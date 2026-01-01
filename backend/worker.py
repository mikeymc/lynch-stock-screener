# ABOUTME: Background worker process for executing long-running jobs
# ABOUTME: Polls PostgreSQL for jobs, executes screening and SEC refresh tasks

# CRITICAL: Disable yfinance's SQLite caches BEFORE any other imports
# to prevent "database is locked" errors under concurrent thread access.
# This must be at the very top of the file.
import yfinance.cache as _yf_cache

def _init_dummy_tz_cache(self, cache_dir=None):
    self._cache = _yf_cache._TzCacheDummy()

def _init_dummy_cookie_cache(self, cache_dir=None):
    self._cache = _yf_cache._CookieCacheDummy()

# Monkey-patch the initialise methods to use dummy caches
_yf_cache._TzCacheManager.initialise = _init_dummy_tz_cache
_yf_cache._CookieCacheManager.initialise = _init_dummy_cookie_cache

# Also patch the get_*_cache functions to return global dummy instances immediately
_yf_cache._tz_cache = _yf_cache._TzCacheDummy()
_yf_cache._cookie_cache = _yf_cache._CookieCacheDummy()

# Override the get functions to return our dummy caches
_yf_cache.get_tz_cache = lambda: _yf_cache._tz_cache
_yf_cache.get_cookie_cache = lambda: _yf_cache._cookie_cache

print("[Worker] yfinance SQLite cache disabled (using dummy caches)")
# End yfinance cache patch

import os
import sys
import time
import signal
import logging
import socket
import gc
import resource
import platform
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Dict, Any
from threading import Semaphore

# Import fetcher modules for data caching
from price_history_fetcher import PriceHistoryFetcher
from sec_data_fetcher import SECDataFetcher
from news_fetcher import NewsFetcher
from material_events_fetcher import MaterialEventsFetcher

# Import global rate limiter for SEC API (shared across all threads)
from sec_rate_limiter import SEC_RATE_LIMITER, configure_edgartools_rate_limit

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Suppress verbose HTTP and SEC library logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('edgar').setLevel(logging.WARNING)
logging.getLogger('edgar.httprequests').setLevel(logging.WARNING)
logging.getLogger('hpack').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Configuration
IDLE_SHUTDOWN_SECONDS = int(os.environ.get('WORKER_IDLE_TIMEOUT', 300))  # 5 minutes
HEARTBEAT_INTERVAL = 60  # Extend claim every 60 seconds
POLL_INTERVAL = 5  # Check for new jobs every 5 seconds


def get_memory_mb() -> float:
    """Get current RSS memory usage in MB"""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS returns bytes, Linux returns KB
    if platform.system() == 'Darwin':
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024


# Memory alerting thresholds (based on 4GB worker allocation)
MEMORY_WARNING_MB = 3200   # 80% of 4GB - log warning
MEMORY_CRITICAL_MB = 3800  # 95% of 4GB - log critical


def check_memory_warning(context: str = "") -> None:
    """
    Check memory usage and log warnings if approaching limits.
    Call this periodically during long-running jobs.
    """
    used_mb = get_memory_mb()
    
    if used_mb >= MEMORY_CRITICAL_MB:
        logger.critical(
            f"🚨 CRITICAL MEMORY: {used_mb:.0f}MB used (limit ~4096MB) - OOM risk! {context}"
        )
    elif used_mb >= MEMORY_WARNING_MB:
        logger.warning(
            f"⚠️ HIGH MEMORY: {used_mb:.0f}MB used (warning threshold: {MEMORY_WARNING_MB}MB) {context}"
        )



class BackgroundWorker:
    """Background worker that polls for and executes jobs from PostgreSQL"""

    def __init__(self):
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"
        self.shutdown_requested = False
        self.current_job_id = None
        self.last_job_time = time.time()
        self.last_heartbeat = time.time()

        # Initialize database connection
        from database import Database
        self.db = Database(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=int(os.environ.get('DB_PORT', 5432)),
            database=os.environ.get('DB_NAME', 'lynch_stocks'),
            user=os.environ.get('DB_USER', 'lynch'),
            password=os.environ.get('DB_PASSWORD', 'lynch_dev_password')
        )

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        logger.info(f"Worker {self.worker_id} initialized")

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_requested = True

        # Release current job back to pending if we have one
        if self.current_job_id:
            logger.info(f"Releasing job {self.current_job_id} back to pending")
            self.db.release_job(self.current_job_id)

    def run(self):
        """Main worker loop"""
        logger.info(f"Worker {self.worker_id} starting main loop")
        if IDLE_SHUTDOWN_SECONDS > 0:
            logger.info(f"Idle shutdown: {IDLE_SHUTDOWN_SECONDS}s, Poll interval: {POLL_INTERVAL}s")
        else:
            logger.info(f"Idle shutdown: DISABLED, Poll interval: {POLL_INTERVAL}s")

        while not self.shutdown_requested:
            # Check for idle shutdown (skip if IDLE_SHUTDOWN_SECONDS is 0)
            if IDLE_SHUTDOWN_SECONDS > 0:
                idle_time = time.time() - self.last_job_time
                if idle_time > IDLE_SHUTDOWN_SECONDS:
                    logger.info(f"Idle for {idle_time:.0f}s (limit: {IDLE_SHUTDOWN_SECONDS}s), shutting down")
                    break

            # Try to claim a job
            job = self.db.claim_pending_job(self.worker_id)

            if job:
                self.current_job_id = job['id']
                logger.info(f"Claimed job {job['id']} (type: {job['job_type']})")

                try:
                    self._execute_job(job)
                except Exception as e:
                    logger.error(f"Job {job['id']} failed: {e}")
                    import traceback
                    traceback.print_exc()
                    self.db.fail_job(job['id'], str(e))
                finally:
                    self.current_job_id = None
                    # Reset idle timer AFTER job completes, not when claimed
                    self.last_job_time = time.time()
            else:
                # No jobs available, wait before polling again
                time.sleep(POLL_INTERVAL)

        logger.info(f"Worker {self.worker_id} shutting down")

    def _execute_job(self, job: Dict[str, Any]):
        """Execute a job based on its type"""
        job_id = job['id']
        job_type = job['job_type']
        params = job['params']

        # Mark job as running
        self.db.update_job_status(job_id, 'running')

        if job_type == 'full_screening':
            self._run_screening(job_id, params)
        elif job_type == 'sec_refresh':
            self._run_sec_refresh(job_id, params)
        elif job_type == 'price_history_cache':
            self._run_price_history_cache(job_id, params)
        elif job_type == 'news_cache':
            self._run_news_cache(job_id, params)
        elif job_type == '10k_cache':
            self._run_10k_cache(job_id, params)
        elif job_type == '8k_cache':
            self._run_8k_cache(job_id, params)
        elif job_type == 'form4_cache':
            self._run_form4_cache(job_id, params)
        elif job_type == 'outlook_cache':
            self._run_outlook_cache(job_id, params)
        elif job_type == 'transcript_cache':
            self._run_transcript_cache(job_id, params)
        else:
            raise ValueError(f"Unknown job type: {job_type}")

    def _send_heartbeat(self, job_id: int):
        """Send heartbeat to extend job claim"""
        now = time.time()
        if now - self.last_heartbeat >= HEARTBEAT_INTERVAL:
            self.db.extend_job_claim(job_id)
            self.last_heartbeat = now

    def _run_screening(self, job_id: int, params: Dict[str, Any]):
        """Execute full stock screening"""
        session_id = params.get('session_id')
        algorithm = params.get('algorithm', 'weighted')
        force_refresh = params.get('force_refresh', False)
        limit = params.get('limit')
        region = params.get('region', 'us')  # Default to US only

        from tradingview_fetcher import TradingViewFetcher
        from finviz_fetcher import FinvizFetcher
        from data_fetcher import DataFetcher
        from earnings_analyzer import EarningsAnalyzer
        from lynch_criteria import LynchCriteria
        
        # Initialize fetchers
        fetcher = DataFetcher(self.db)
        analyzer = EarningsAnalyzer(self.db)
        criteria = LynchCriteria(self.db, analyzer)

        # Map CLI region to TradingView regions
        region_mapping = {
            'us': ['us'],                       # US only
            'north-america': ['north_america'], # US + Canada + Mexico
            'south-america': ['south_america'], # South America
            'europe': ['europe'],
            'asia': ['asia'],                   # Asia including China & India
            'all': None                         # None = all regions
        }
        tv_regions = region_mapping.get(region, ['us'])
        
        # Bulk prefetch market data
        self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching market data from TradingView ({region})...')
        tv_fetcher = TradingViewFetcher()
        
        # Note: TradingViewFetcher.fetch_all_stocks handles the region keys defined above
        market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
        logger.info(f"Loaded {len(market_data_cache)} stocks from TradingView ({region})")

        self._send_heartbeat(job_id)

        # Bulk prefetch institutional ownership
        self.db.update_job_progress(job_id, progress_pct=10, progress_message='Fetching institutional ownership from Finviz...')
        finviz_fetcher = FinvizFetcher()
        finviz_cache = finviz_fetcher.fetch_all_institutional_ownership(limit=20000)
        logger.info(f"Loaded {len(finviz_cache)} institutional ownership values from Finviz")

        self._send_heartbeat(job_id)

        # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
        filtered_symbols = list(market_data_cache.keys())

        # Apply limit if specified
        if limit and limit < len(filtered_symbols):
            filtered_symbols = filtered_symbols[:limit]

        total = len(filtered_symbols)
        self.db.update_job_progress(job_id, progress_pct=15, progress_message=f'Screening {total} stocks...',
                                    total_count=total)

        # Create session if one wasn't provided (e.g., from GitHub Actions via /api/jobs)
        if not session_id:
            session_id = self.db.create_session(algorithm=algorithm, total_count=total)
            logger.info(f"Created screening session {session_id}")
        else:
            # Update session total count if we have an existing session
            self.db.update_session_total_count(session_id, total)

        logger.info(f"Ready to screen {total} stocks (session_id={session_id})")

        # Process stocks
        def process_stock(symbol):
            try:
                # 1. Fetch stock data (uses TradingView cache for metrics)
                stock_data = fetcher.fetch_stock_data(symbol, force_refresh,
                                                      market_data_cache=market_data_cache,
                                                      finviz_cache=finviz_cache)
                if not stock_data:
                    return None

                # 2. Evaluate stock against Lynch criteria
                evaluation = criteria.evaluate_stock(symbol, algorithm=algorithm)
                if not evaluation:
                    return None

                # NOTE: Price history and news caching are now handled by separate jobs:
                # - price_history_cache: Caches weekly price history
                # - news_cache: Caches Finnhub news articles
                # - 10k_cache: Caches 10-K/10-Q sections
                # - 8k_cache: Caches 8-K material events
                # This keeps screening fast - focused only on evaluation.

                # 3. Save screening result
                if session_id:
                    self.db.save_screening_result(session_id, evaluation)
                return evaluation

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                return None

        # Initialize counters
        pass_count = 0
        close_count = 0
        fail_count = 0
        total_analyzed = 0
        processed_count = 0
        failed_symbols = []

        BATCH_SIZE = 10
        MAX_WORKERS = 40
        BATCH_DELAY = 0.5

        def update_counters(evaluation):
            nonlocal pass_count, close_count, fail_count, total_analyzed
            total_analyzed += 1
            status = evaluation.get('overall_status')
            
            if algorithm == 'classic':
                if status == 'PASS':
                    pass_count += 1
                elif status == 'CLOSE':
                    close_count += 1
                elif status == 'FAIL':
                    fail_count += 1
            else:
                if status in ['STRONG_BUY', 'BUY']:
                    pass_count += 1
                elif status == 'HOLD':
                    close_count += 1
                elif status in ['CAUTION', 'AVOID']:
                    fail_count += 1

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for batch_start in range(0, total, BATCH_SIZE):
                if self.shutdown_requested:
                    logger.info("Shutdown requested, stopping screening")
                    self.db.release_job(job_id)
                    return
                
                # Check if job was cancelled
                job_status = self.db.get_background_job(job_id)
                if job_status and job_status.get('status') == 'cancelled':
                    logger.info(f"Job {job_id} was cancelled, stopping screening")
                    return

                batch_end = min(batch_start + BATCH_SIZE, total)
                batch = filtered_symbols[batch_start:batch_end]

                future_to_symbol = {executor.submit(process_stock, symbol): symbol for symbol in batch}

                for future in as_completed(future_to_symbol):
                    symbol = future_to_symbol[future]
                    processed_count += 1

                    try:
                        evaluation = future.result()
                        if evaluation:
                            update_counters(evaluation)
                        else:
                            failed_symbols.append(symbol)
                        
                        # AGGRESSIVE CACHE CLEARING to prevent OOM
                        # Immediately remove large data objects for this symbol
                        if symbol in market_data_cache:
                            del market_data_cache[symbol]
                        if symbol in finviz_cache:
                            del finviz_cache[symbol]

                    except Exception as e:
                        logger.error(f"Error getting result for {symbol}: {e}")
                        failed_symbols.append(symbol)

                # Update progress
                progress_pct = 15 + int((processed_count / total) * 80)  # 15-95%
                self.db.update_job_progress(job_id, progress_pct=progress_pct,
                                            progress_message=f'Processed {processed_count}/{total}',
                                            processed_count=processed_count)
                
                logger.info(f"========== SCREENING PROGRESS: {processed_count}/{total} ({progress_pct}%) | MEMORY: {get_memory_mb():.0f}MB ==========")
                check_memory_warning(f"[screening {processed_count}/{total}]")
                
                # Periodic garbage collection to prevent memory buildup
                if batch_start % 100 == 0:
                    gc.collect()

                if session_id:
                    self.db.update_session_progress(session_id, processed_count, symbol)

                self._send_heartbeat(job_id)

                if batch_end < total:
                    time.sleep(BATCH_DELAY)

        # Retry failed symbols
        if failed_symbols:
            logger.info(f"Retrying {len(failed_symbols)} failed stocks")
            self.db.update_job_progress(job_id, progress_pct=96, progress_message='Retrying failed stocks...')
            time.sleep(5)

            for symbol in failed_symbols:
                if self.shutdown_requested:
                    break
                try:
                    evaluation = process_stock(symbol)
                    if evaluation:
                        update_counters(evaluation)
                        
                    # Also clear cache for retries
                    if symbol in market_data_cache:
                        del market_data_cache[symbol]
                    if symbol in finviz_cache:
                        del finviz_cache[symbol]
                        
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Retry error for {symbol}: {e}")

        # Complete job
        result = {
            'total_analyzed': total_analyzed,
            'pass_count': pass_count,
            'close_count': close_count,
            'fail_count': fail_count,
            'session_id': session_id
        }
        self.db.complete_job(job_id, result)
        logger.info(f"Screening complete: {total_analyzed} stocks analyzed")

    def _run_sec_refresh(self, job_id: int, params: Dict[str, Any]):
        """Execute SEC data refresh"""
        from migrate_sec_to_postgres import SECPostgresMigrator

        logger.info(f"Starting SEC refresh job {job_id}")

        self.db.update_job_progress(job_id, progress_pct=5, progress_message='Initializing SEC migrator...')

        # Create migrator with same DB connection params
        migrator = SECPostgresMigrator(
            db_host=os.environ.get('DB_HOST', 'localhost'),
            db_port=int(os.environ.get('DB_PORT', 5432)),
            db_name=os.environ.get('DB_NAME', 'lynch_stocks'),
            db_user=os.environ.get('DB_USER', 'lynch'),
            db_password=os.environ.get('DB_PASSWORD', 'lynch_dev_password')
        )

        try:
            migrator.connect()
            self.db.update_job_progress(job_id, progress_pct=10, progress_message='Downloading SEC data...')

            # Progress callback
            def progress_callback(current, total, message):
                if total > 0:
                    pct = 10 + int((current / total) * 85)  # 10-95%
                else:
                    pct = 50
                self.db.update_job_progress(job_id, progress_pct=pct,
                                            progress_message=message,
                                            processed_count=current,
                                            total_count=total)
                self._send_heartbeat(job_id)

            # Run migration
            migrator.migrate_from_zip_stream(progress_callback=progress_callback)

            self.db.complete_job(job_id, {'status': 'completed'})
            logger.info("SEC refresh complete")

        except Exception as e:
            logger.error(f"SEC refresh failed: {e}")
            raise
        finally:
            migrator.close()

    def _run_price_history_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache weekly price history for all stocks via yfinance.
        
        Uses TradingView to get stock list (same as screening) to ensure we cache
        prices for all stocks that will be screened, not just those already in DB.
        
        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            force_refresh: If True, bypass cache and fetch fresh data
        """
        limit = params.get('limit')
        region = params.get('region', 'us')
        
        logger.info(f"Starting price history cache job {job_id} (region={region})")
        
        from yfinance_price_client import YFinancePriceClient
        from tradingview_fetcher import TradingViewFetcher
        
        # Map CLI region to TradingView regions (same as screening)
        region_mapping = {
            'us': ['us'],
            'north-america': ['north_america'],
            'south-america': ['south_america'],
            'europe': ['europe'],
            'asia': ['asia'],
            'all': None  # All regions
        }
        tv_regions = region_mapping.get(region, ['us'])
        
        # Get stock list from TradingView (same as screening does)
        self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
        tv_fetcher = TradingViewFetcher()
        market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
        
        # Ensure all stocks exist in DB before caching (prevents FK violations)
        self.db.update_job_progress(job_id, progress_pct=8, progress_message='Ensuring stocks exist in database...')
        self.db.ensure_stocks_exist_batch(market_data_cache)
        
        # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
        all_symbols = list(market_data_cache.keys())
        
        # Apply limit if specified
        if limit and limit < len(all_symbols):
            all_symbols = all_symbols[:limit]
        
        total = len(all_symbols)
        logger.info(f"Caching price history for {total} stocks (ordered by score)")
        
        # Get force_refresh param
        force_refresh = params.get('force_refresh', False)
        
        # Calculate week start (most recent Saturday) for cache checking
        # This ensures we only re-fetch once per fiscal week
        from datetime import datetime, timedelta
        today = datetime.now()
        days_since_saturday = (today.weekday() + 2) % 7  # Saturday = 0 days back on Saturday
        week_start = (today - timedelta(days=days_since_saturday)).strftime('%Y-%m-%d')
        
        # Filter out symbols already checked this week (unless force_refresh)
        skipped = 0
        if not force_refresh:
            symbols_to_process = []
            for symbol in all_symbols:
                if self.db.was_cache_checked_since(symbol, 'prices', week_start):
                    skipped += 1
                else:
                    symbols_to_process.append(symbol)
            
            if skipped > 0:
                logger.info(f"Price history cache: skipped {skipped} symbols already checked since {week_start}")
            all_symbols = symbols_to_process
        
        total_to_process = len(all_symbols)
        logger.info(f"Processing {total_to_process} stocks for price history (skipped {skipped})")
        
        self.db.update_job_progress(job_id, progress_pct=10, 
                                    progress_message=f'Caching price history for {total_to_process} stocks (skipped {skipped})...',
                                    total_count=total_to_process)
        
        # Initialize fetchers
        price_client = YFinancePriceClient()
        # Note: Rate limiting is handled by global YFINANCE_SEMAPHORE in yfinance_rate_limiter.py
        price_history_fetcher = PriceHistoryFetcher(self.db, price_client, yf_semaphore=None)
        
        processed = 0
        cached = 0
        errors = 0

        
        # Process in batches with threading for performance
        # Reduced from 50/12 to 25/6 to prevent OOM on 2GB workers (yfinance DataFrames accumulate)
        BATCH_SIZE = 25
        MAX_WORKERS = 6
        
        for batch_start in range(0, total_to_process, BATCH_SIZE):
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping price history cache job")
                break
            
            # Check if job was cancelled
            job_status = self.db.get_background_job(job_id)
            if job_status and job_status.get('status') == 'cancelled':
                logger.info(f"Job {job_id} was cancelled, stopping")
                return
            
            batch_end = min(batch_start + BATCH_SIZE, total_to_process)
            batch = all_symbols[batch_start:batch_end]
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(price_history_fetcher.fetch_and_cache_prices, symbol): symbol for symbol in batch}
                
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        future.result()
                        cached += 1
                        # Record successful cache check with today's date as last_data_date
                        self.db.record_cache_check(symbol, 'prices', today.strftime('%Y-%m-%d'))
                    except Exception as e:
                        logger.debug(f"[{symbol}] Price history cache error: {e}")
                        errors += 1
                    processed += 1
            
            # Update progress
            if processed % 100 == 0 or batch_end == total_to_process:
                pct = 10 + int((processed / total_to_process) * 85)
                self.db.update_job_progress(
                    job_id, 
                    progress_pct=pct,
                    progress_message=f'Cached {processed}/{total_to_process} stocks ({cached} successful, {errors} errors, {skipped} skipped)',
                    processed_count=processed,
                    total_count=total_to_process
                )
                self._send_heartbeat(job_id)
                logger.info(f"Price history cache progress: {processed}/{total_to_process} (cached: {cached}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                check_memory_warning(f"[price_history {processed}/{total_to_process}]")
        
        # Complete job
        result = {
            'total_stocks': total,  # Original total before skipping
            'processed': processed,
            'cached': cached,
            'skipped': skipped,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"Price history cache complete: {result}")

    def _run_news_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache news articles for all stocks via Finnhub.
        
        Uses TradingView to get stock list (same as screening/prices) with region filtering.
        Symbols are sorted by score (STRONG_BUY first) when available.
        
        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
        """
        limit = params.get('limit')
        region = params.get('region', 'us')
        
        logger.info(f"Starting news cache job {job_id} (region={region})")
        
        from finnhub_news import FinnhubNewsClient
        from tradingview_fetcher import TradingViewFetcher
        
        # Map CLI region to TradingView regions (same as screening/prices)
        region_mapping = {
            'us': ['us'],
            'north-america': ['north_america'],
            'south-america': ['south_america'],
            'europe': ['europe'],
            'asia': ['asia'],
            'all': None  # All regions
        }
        tv_regions = region_mapping.get(region, ['us'])
        
        # Get stock list from TradingView (same as screening/prices)
        self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
        tv_fetcher = TradingViewFetcher()
        market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
        
        # Ensure all stocks exist in DB before caching (prevents FK violations)
        self.db.update_job_progress(job_id, progress_pct=8, progress_message='Ensuring stocks exist in database...')
        self.db.ensure_stocks_exist_batch(market_data_cache)
        
        # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
        all_symbols = list(market_data_cache.keys())
        
        # Sort by screening score if available (prioritize STRONG_BUY stocks)
        scored_symbols = self.db.get_stocks_ordered_by_score(limit=None)
        scored_set = set(scored_symbols)
        
        # Put scored symbols first (in score order), then remaining unscored symbols
        sorted_symbols = [s for s in scored_symbols if s in set(all_symbols)]
        remaining = [s for s in all_symbols if s not in scored_set]
        all_symbols = sorted_symbols + remaining
        
        # Apply limit if specified
        if limit and limit < len(all_symbols):
            all_symbols = all_symbols[:limit]
        
        total = len(all_symbols)
        logger.info(f"Caching news for {total} stocks (region={region}, sorted by score)")
        
        self.db.update_job_progress(job_id, progress_pct=10,
                                    progress_message=f'Caching news for {total} stocks...',
                                    processed_count=0,
                                    total_count=total)
        
        # Initialize fetcher with API key
        finnhub_api_key = os.environ.get('FINNHUB_API_KEY')
        if not finnhub_api_key:
            error_msg = "FINNHUB_API_KEY not set - cannot cache news"
            logger.error(error_msg)
            self.db.fail_job(job_id, error_msg)
            return
        
        finnhub_client = FinnhubNewsClient(api_key=finnhub_api_key)
        news_fetcher = NewsFetcher(self.db, finnhub_client)
        
        processed = 0
        cached = 0
        errors = 0
        
        for symbol in all_symbols:
            # Check for shutdown/cancellation
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping news cache job")
                break
            
            # Check if job was cancelled
            job_status = self.db.get_background_job(job_id)
            if job_status and job_status.get('status') == 'cancelled':
                logger.info(f"Job {job_id} was cancelled, stopping")
                return
            
            try:
                news_fetcher.fetch_and_cache_news(symbol)
                cached += 1
            except Exception as e:
                logger.debug(f"[{symbol}] News cache error: {e}")
                errors += 1
            
            processed += 1
            
            # Update progress every 50 stocks
            if processed % 50 == 0:
                pct = 10 + int((processed / total) * 85)
                self.db.update_job_progress(
                    job_id,
                    progress_pct=pct,
                    progress_message=f'Cached {processed}/{total} stocks ({cached} successful, {errors} errors)',
                    processed_count=processed,
                    total_count=total
                )
                self._send_heartbeat(job_id)
            
            if processed % 100 == 0:
                logger.info(f"News cache progress: {processed}/{total} (cached: {cached}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                check_memory_warning(f"[news {processed}/{total}]")
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"News cache complete: {result}")


    def _run_10k_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache 10-K and 10-Q filings/sections for all stocks.
        
        Uses TradingView to get stock list (same as screening/prices) with region filtering.
        Symbols are sorted by score (STRONG_BUY first) when available.
        Sequential processing due to SEC rate limits.
        
        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            force_refresh: If True, bypass cache and fetch fresh data
            symbols: Optional list of specific symbols to process (for testing)
            use_rss: If True, use RSS feed to pre-filter to only stocks with new filings
        """
        limit = params.get('limit')
        region = params.get('region', 'us')
        force_refresh = params.get('force_refresh', False)
        specific_symbols = params.get('symbols')  # Optional list of specific symbols
        use_rss = params.get('use_rss', False)
        
        logger.info(f"Starting 10-K/10-Q cache job {job_id} (region={region}, use_rss={use_rss})")
        
        from edgar_fetcher import EdgarFetcher
        from tradingview_fetcher import TradingViewFetcher
        
        # Disable edgartools disk caching - not useful for batch jobs on ephemeral workers
        # (each stock is only processed once, cache would be discarded anyway)
        try:
            from edgar import httpclient
            httpclient.CACHE_DIRECTORY = None
            logger.info("Disabled edgartools HTTP disk cache for batch job")
        except Exception as e:
            logger.warning(f"Could not disable edgartools cache: {e}")
        
        # If specific symbols provided, use those directly (for testing)
        if specific_symbols:
            all_symbols = specific_symbols
            logger.info(f"Using specific symbols: {all_symbols}")
            # Ensure these stocks exist in DB
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Processing {len(all_symbols)} specific symbols...')
        else:
            # Map CLI region to TradingView regions (same as screening/prices)
            region_mapping = {
                'us': ['us'],
                'north-america': ['north_america'],
                'south-america': ['south_america'],
                'europe': ['europe'],
                'asia': ['asia'],
                'all': None  # All regions
            }
            tv_regions = region_mapping.get(region, ['us'])
            
            # Get stock list from TradingView (same as prices does)
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
            tv_fetcher = TradingViewFetcher()
            market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
            
            # Ensure all stocks exist in DB before caching (prevents FK violations)
            self.db.update_job_progress(job_id, progress_pct=8, progress_message='Ensuring stocks exist in database...')
            self.db.ensure_stocks_exist_batch(market_data_cache)
            
            # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
            all_symbols = list(market_data_cache.keys())
            
            # Sort by screening score if available (prioritize STRONG_BUY stocks)
            scored_symbols = self.db.get_stocks_ordered_by_score(limit=None)
            scored_set = set(scored_symbols)
            
            # Put scored symbols first (in score order), then remaining unscored symbols
            sorted_symbols = [s for s in scored_symbols if s in set(all_symbols)]
            remaining = [s for s in all_symbols if s not in scored_set]
            all_symbols = sorted_symbols + remaining
        
        # Apply limit if specified
        if limit and limit < len(all_symbols):
            all_symbols = all_symbols[:limit]
        
        # RSS-based optimization: only process stocks with new filings
        if use_rss and not force_refresh and not specific_symbols:
            from sec_rss_client import SECRSSClient
            self.db.update_job_progress(job_id, progress_pct=9, progress_message='Checking RSS feed for new 10-K/10-Q filings...')
            
            sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
            rss_client = SECRSSClient(sec_user_agent)
            
            # Get tickers with new 10-K OR 10-Q filings from RSS
            known_tickers = set(all_symbols)
            tickers_10k = rss_client.get_tickers_with_new_filings('10-K', known_tickers=known_tickers)
            tickers_10q = rss_client.get_tickers_with_new_filings('10-Q', known_tickers=known_tickers)
            tickers_with_filings = tickers_10k | tickers_10q
            
            if tickers_with_filings:
                # Filter to only stocks with new filings, preserving order
                all_symbols = [s for s in all_symbols if s in tickers_with_filings]
                logger.info(f"RSS optimization: reduced from {len(known_tickers)} to {len(all_symbols)} stocks with new 10-K/10-Q filings")
            else:
                logger.info("RSS optimization: no new 10-K/10-Q filings found, skipping cache job")
                self.db.complete_job(job_id, {'total_stocks': 0, 'processed': 0, 'cached': 0, 'errors': 0, 'rss_optimized': True})
                return
        
        total = len(all_symbols)
        logger.info(f"Caching 10-K/10-Q for {total} stocks (region={region}, sorted by score)")
        
        # Initialize SEC fetcher with CIK cache
        sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
        logger.info("Pre-fetching SEC CIK mappings...")
        cik_cache = EdgarFetcher.prefetch_cik_cache(sec_user_agent)
        
        edgar_fetcher = EdgarFetcher(
            user_agent=sec_user_agent,
            db=self.db,
            cik_cache=cik_cache
        )
        sec_data_fetcher = SECDataFetcher(self.db, edgar_fetcher)
        
        self.db.update_job_progress(job_id, progress_pct=10,
                                    progress_message=f'Caching 10-K/10-Q for {total} stocks...',
                                    total_count=total)
        
        processed = 0
        cached = 0
        errors = 0
        
        for symbol in all_symbols:
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping 10-K cache job")
                break
            
            # Check if job was cancelled
            job_status = self.db.get_background_job(job_id)
            if job_status and job_status.get('status') == 'cancelled':
                logger.info(f"Job {job_id} was cancelled, stopping")
                return
            
            try:
                sec_data_fetcher.fetch_and_cache_all(symbol, force_refresh=force_refresh)
                cached += 1
            except Exception as e:
                logger.debug(f"[{symbol}] 10-K/10-Q cache error: {e}")
                errors += 1
            
            processed += 1
            
            # Update progress every 25 stocks (slower due to rate limits)
            if processed % 25 == 0:
                pct = 10 + int((processed / total) * 85)
                self.db.update_job_progress(
                    job_id,
                    progress_pct=pct,
                    progress_message=f'Cached {processed}/{total} stocks ({cached} successful, {errors} errors)',
                    processed_count=processed,
                    total_count=total
                )
                self._send_heartbeat(job_id)
            
            if processed % 10 == 0:
                logger.info(f"10-K/10-Q cache progress: {processed}/{total} (cached: {cached}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                check_memory_warning(f"[10k {processed}/{total}]")
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"10-K/10-Q cache complete: {result}")

    def _run_8k_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache 8-K material events for all stocks.
        
        Uses TradingView to get stock list (same as screening/prices) with region filtering.
        Symbols are sorted by score (STRONG_BUY first) when available.
        Sequential processing due to SEC rate limits.
        Uses incremental fetching - only fetches events newer than last cached.
        
        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            force_refresh: If True, bypass cache and fetch fresh data
            use_rss: If True, use RSS feed to pre-filter to only stocks with new filings
        """
        limit = params.get('limit')
        region = params.get('region', 'us')
        force_refresh = params.get('force_refresh', False)
        use_rss = params.get('use_rss', False)
        
        logger.info(f"Starting 8-K cache job {job_id} (region={region}, use_rss={use_rss})")
        
        from edgar_fetcher import EdgarFetcher
        from sec_8k_client import SEC8KClient
        from tradingview_fetcher import TradingViewFetcher
        
        # Disable edgartools disk caching - not useful for batch jobs on ephemeral workers
        # (each stock is only processed once, cache would be discarded anyway)
        try:
            from edgar import httpclient
            httpclient.CACHE_DIRECTORY = None
            logger.info("Disabled edgartools HTTP disk cache for batch job")
        except Exception as e:
            logger.warning(f"Could not disable edgartools cache: {e}")
        
        # Map CLI region to TradingView regions (same as screening/prices)
        region_mapping = {
            'us': ['us'],
            'north-america': ['north_america'],
            'south-america': ['south_america'],
            'europe': ['europe'],
            'asia': ['asia'],
            'all': None  # All regions
        }
        tv_regions = region_mapping.get(region, ['us'])
        
        # Get stock list from TradingView (same as prices does)
        self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
        tv_fetcher = TradingViewFetcher()
        market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
        
        # Ensure all stocks exist in DB before caching (prevents FK violations)
        self.db.update_job_progress(job_id, progress_pct=8, progress_message='Ensuring stocks exist in database...')
        self.db.ensure_stocks_exist_batch(market_data_cache)
        
        # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
        all_symbols = list(market_data_cache.keys())
        
        # Sort by screening score if available (prioritize STRONG_BUY stocks)
        scored_symbols = self.db.get_stocks_ordered_by_score(limit=None)
        scored_set = set(scored_symbols)
        
        # Put scored symbols first (in score order), then remaining unscored symbols
        sorted_symbols = [s for s in scored_symbols if s in set(all_symbols)]
        remaining = [s for s in all_symbols if s not in scored_set]
        all_symbols = sorted_symbols + remaining
        
        # Apply limit if specified
        if limit and limit < len(all_symbols):
            all_symbols = all_symbols[:limit]
        
        # RSS-based optimization: only process stocks with new filings
        if use_rss and not force_refresh:
            from sec_rss_client import SECRSSClient
            self.db.update_job_progress(job_id, progress_pct=9, progress_message='Checking RSS feed for new 8-K filings...')
            
            sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
            rss_client = SECRSSClient(sec_user_agent)
            
            # Get tickers with new 8-K filings from RSS
            known_tickers = set(all_symbols)
            tickers_with_filings = rss_client.get_tickers_with_new_filings('8-K', known_tickers=known_tickers)
            
            if tickers_with_filings:
                # Filter to only stocks with new filings, preserving order
                all_symbols = [s for s in all_symbols if s in tickers_with_filings]
                logger.info(f"RSS optimization: reduced from {len(known_tickers)} to {len(all_symbols)} stocks with new 8-K filings")
            else:
                logger.info("RSS optimization: no new 8-K filings found, skipping cache job")
                self.db.complete_job(job_id, {'total_stocks': 0, 'processed': 0, 'cached': 0, 'errors': 0, 'rss_optimized': True})
                return
        
        total = len(all_symbols)
        logger.info(f"Caching 8-K events for {total} stocks (region={region}, sorted by score)")
        
        # Initialize SEC fetchers with CIK cache
        sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
        logger.info("Pre-fetching SEC CIK mappings...")
        cik_cache = EdgarFetcher.prefetch_cik_cache(sec_user_agent)
        
        edgar_fetcher = EdgarFetcher(
            user_agent=sec_user_agent,
            db=self.db,
            cik_cache=cik_cache
        )
        sec_8k_client = SEC8KClient(
            user_agent=sec_user_agent,
            edgar_fetcher=edgar_fetcher
        )
        events_fetcher = MaterialEventsFetcher(self.db, sec_8k_client)
        
        self.db.update_job_progress(job_id, progress_pct=10,
                                    progress_message=f'Caching 8-K events for {total} stocks...',
                                    total_count=total)
        
        processed = 0
        cached = 0
        errors = 0
        
        for symbol in all_symbols:
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping 8-K cache job")
                break
            
            # Check if job was cancelled
            job_status = self.db.get_background_job(job_id)
            if job_status and job_status.get('status') == 'cancelled':
                logger.info(f"Job {job_id} was cancelled, stopping")
                return
            
            try:
                events_fetcher.fetch_and_cache_events(symbol, force_refresh=force_refresh)
                cached += 1
            except Exception as e:
                logger.debug(f"[{symbol}] 8-K cache error: {e}")
                errors += 1
            
            processed += 1
            
            # Update progress every 25 stocks (slower due to rate limits)
            if processed % 25 == 0:
                pct = 10 + int((processed / total) * 85)
                self.db.update_job_progress(
                    job_id,
                    progress_pct=pct,
                    progress_message=f'Cached {processed}/{total} stocks ({cached} successful, {errors} errors)',
                    processed_count=processed,
                    total_count=total
                )
                self._send_heartbeat(job_id)
            
            if processed % 10 == 0:
                logger.info(f"8-K cache progress: {processed}/{total} (cached: {cached}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                check_memory_warning(f"[8k {processed}/{total}]")
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"8-K cache complete: {result}")

    def _run_form4_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache SEC Form 4 insider transaction filings for all stocks.
        
        Fetches Form 4 filings from SEC EDGAR and parses XML to extract:
        - Transaction codes (P=Purchase, S=Sale, M=Exercise, A=Award, etc.)
        - 10b5-1 plan indicators
        - Direct/indirect ownership
        - Detailed transaction data
        
        Uses TradingView to get stock list with region filtering.
        Symbols are sorted by score (STRONG_BUY first) when available.
        
        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            use_rss: If True, use RSS feed to pre-filter to only stocks with new filings
        """
        limit = params.get('limit')
        region = params.get('region', 'us')
        use_rss = params.get('use_rss', False)
        
        logger.info(f"Starting Form 4 cache job {job_id} (region={region}, use_rss={use_rss})")
        
        from edgar_fetcher import EdgarFetcher
        from tradingview_fetcher import TradingViewFetcher
        
        # Disable edgartools disk caching for batch jobs
        try:
            from edgar import httpclient
            httpclient.CACHE_DIRECTORY = None
            logger.info("Disabled edgartools HTTP disk cache for batch job")
        except Exception as e:
            logger.warning(f"Could not disable edgartools cache: {e}")
        
        # Map CLI region to TradingView regions
        region_mapping = {
            'us': ['us'],
            'north-america': ['north_america'],
            'south-america': ['south_america'],
            'europe': ['europe'],
            'asia': ['asia'],
            'all': None  # All regions
        }
        tv_regions = region_mapping.get(region, ['us'])
        
        # Get stock list from TradingView
        self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
        tv_fetcher = TradingViewFetcher()
        market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
        
        # Ensure all stocks exist in DB before caching (prevents FK violations)
        self.db.update_job_progress(job_id, progress_pct=8, progress_message='Ensuring stocks exist in database...')
        self.db.ensure_stocks_exist_batch(market_data_cache)
        
        all_symbols = list(market_data_cache.keys())
        
        # Sort by screening score if available (prioritize STRONG_BUY stocks)
        scored_symbols = self.db.get_stocks_ordered_by_score(limit=None)
        scored_set = set(scored_symbols)
        
        sorted_symbols = [s for s in scored_symbols if s in set(all_symbols)]
        remaining = [s for s in all_symbols if s not in scored_set]
        all_symbols = sorted_symbols + remaining
        
        # Apply limit if specified
        if limit and limit < len(all_symbols):
            all_symbols = all_symbols[:limit]
        
        # RSS-based optimization: only process stocks with new filings
        if use_rss:
            from sec_rss_client import SECRSSClient
            self.db.update_job_progress(job_id, progress_pct=9, progress_message='Checking RSS feed for new Form 4 filings...')
            
            sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
            rss_client = SECRSSClient(sec_user_agent)
            
            # Get tickers with new Form 4 filings from RSS
            known_tickers = set(all_symbols)
            tickers_with_filings = rss_client.get_tickers_with_new_filings('FORM4', known_tickers=known_tickers)
            
            if tickers_with_filings:
                # Filter to only stocks with new filings, preserving order
                all_symbols = [s for s in all_symbols if s in tickers_with_filings]
                logger.info(f"RSS optimization: reduced from {len(known_tickers)} to {len(all_symbols)} stocks with new Form 4 filings")
            else:
                logger.info("RSS optimization: no new Form 4 filings found, skipping cache job")
                self.db.complete_job(job_id, {'total_stocks': 0, 'processed': 0, 'cached': 0, 'errors': 0, 'rss_optimized': True})
                return
        
        total = len(all_symbols)
        logger.info(f"Caching Form 4 filings for {total} stocks (region={region}, sorted by score)")
        
        # Initialize SEC fetcher with CIK cache
        sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
        logger.info("Pre-fetching SEC CIK mappings...")
        cik_cache = EdgarFetcher.prefetch_cik_cache(sec_user_agent)
        
        edgar_fetcher = EdgarFetcher(
            user_agent=sec_user_agent,
            db=self.db,
            cik_cache=cik_cache
        )
        
        self.db.update_job_progress(job_id, progress_pct=10,
                                    progress_message=f'Caching Form 4 for {total} stocks...',
                                    total_count=total)
        
        processed = 0
        cached = 0
        skipped = 0
        errors = 0
        total_transactions = 0
        
        # Calculate since_date for cache checking (same as fetch_form4_filings default)
        from datetime import datetime, timedelta
        one_year_ago = datetime.now() - timedelta(days=365)
        since_date = one_year_ago.strftime('%Y-%m-%d')
        
        # Get force_refresh param (default False)
        force_refresh = params.get('force_refresh', False)
        
        for symbol in all_symbols:
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping Form 4 cache job")
                break
            
            # Check if job was cancelled
            job_status = self.db.get_background_job(job_id)
            if job_status and job_status.get('status') == 'cancelled':
                logger.info(f"Job {job_id} was cancelled, stopping")
                return
            
            # Skip if we already checked this symbol recently (unless force_refresh)
            # This prevents redundant API calls even for symbols with no transactions
            if not force_refresh:
                # Check 1: Do we have actual transaction data since since_date?
                if self.db.has_recent_insider_trades(symbol, since_date):
                    skipped += 1
                    processed += 1
                    if skipped % 100 == 0:
                        logger.info(f"Form 4 cache: skipped {skipped} already-cached symbols")
                    continue
                
                # Check 2: Did we already check this symbol today (even if no data was found)?
                today = datetime.now().strftime('%Y-%m-%d')
                if self.db.was_cache_checked_since(symbol, 'form4', today):
                    skipped += 1
                    processed += 1
                    if skipped % 100 == 0:
                        logger.info(f"Form 4 cache: skipped {skipped} already-cached symbols")
                    continue
            
            try:
                # Fetch and parse Form 4 filings
                transactions = edgar_fetcher.fetch_form4_filings(symbol)
                
                # Find most recent transaction date for cache tracking
                last_data_date = None
                if transactions:
                    # Save to database with enriched data
                    self.db.save_insider_trades(symbol, transactions)
                    total_transactions += len(transactions)
                    cached += 1
                    
                    # Get the most recent transaction date
                    dates = [t.get('transaction_date') for t in transactions if t.get('transaction_date')]
                    if dates:
                        last_data_date = max(dates)
                    
                    # Calculate Insider Net Buying (Last 6 Months)
                    # Use accurate Form 4 data (Buy = P, Sell = S/F/D)
                    from datetime import datetime, timedelta
                    cutoff_date = datetime.now() - timedelta(days=180)
                    net_buying = 0.0
                    
                    for t in transactions:
                        try:
                            # Form 4 dates are YYYY-MM-DD
                            t_date = datetime.strptime(t['transaction_date'], '%Y-%m-%d')
                            if t_date >= cutoff_date:
                                t_type = t.get('transaction_type') # 'Buy', 'Sell', 'Other'
                                val = t.get('value', 0.0) or 0.0
                                
                                if t_type == 'Buy':
                                    net_buying += val
                                elif t_type == 'Sell':
                                    net_buying -= val
                        except (ValueError, TypeError):
                            continue
                    
                    # Update metrics using partial update (safe thanks to database.py refactor)
                    self.db.save_stock_metrics(symbol, {'insider_net_buying_6m': net_buying})
                else:
                    # No transactions found (not an error, just no Form 4s)
                    cached += 1
                
                # Record that we checked this symbol (even if no data found)
                self.db.record_cache_check(symbol, 'form4', last_data_date)
                    
            except Exception as e:
                logger.debug(f"[{symbol}] Form 4 cache error: {e}")
                errors += 1
            
            processed += 1
            
            # Update progress every 25 stocks
            if processed % 25 == 0:
                pct = 10 + int((processed / total) * 85)
                self.db.update_job_progress(
                    job_id,
                    progress_pct=pct,
                    progress_message=f'Processed {processed}/{total} stocks (cached: {cached}, skipped: {skipped}, errors: {errors})',
                    processed_count=processed,
                    total_count=total
                )
                self._send_heartbeat(job_id)
            
            if processed % 10 == 0:
                logger.info(f"Form 4 cache progress: {processed}/{total} (cached: {cached}, skipped: {skipped}, transactions: {total_transactions}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                check_memory_warning(f"[form4 {processed}/{total}]")
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'skipped': skipped,
            'total_transactions': total_transactions,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"Form 4 cache complete: {result}")

    def _run_outlook_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache forward metrics (forward P/E, PEG, EPS) and insider trades for stocks.
        
        Uses TradingView to get stock list (same as screening/prices) with region filtering.
        Symbols are sorted by score (STRONG_BUY first) when available.
        
        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            symbols: Optional list of specific symbols to process (for testing)
        """
        import yfinance as yf
        import pandas as pd
        from datetime import datetime, timedelta
        from tradingview_fetcher import TradingViewFetcher
        
        limit = params.get('limit')
        region = params.get('region', 'us')
        specific_symbols = params.get('symbols')  # Optional list of specific symbols
        
        logger.info(f"Starting outlook cache job {job_id} (region={region})")
        
        # If specific symbols provided, use those directly (for testing)
        if specific_symbols:
            all_symbols = specific_symbols
            logger.info(f"Using specific symbols: {all_symbols}")
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Processing {len(all_symbols)} specific symbols...')
        else:
            # Map CLI region to TradingView regions (same as screening/prices)
            region_mapping = {
                'us': ['us'],
                'north-america': ['north_america'],
                'south-america': ['south_america'],
                'europe': ['europe'],
                'asia': ['asia'],
                'all': None  # All regions
            }
            tv_regions = region_mapping.get(region, ['us'])
            
            # Get stock list from TradingView (same as screening/prices)
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
            tv_fetcher = TradingViewFetcher()
            market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
            
            # Ensure all stocks exist in DB before caching (prevents FK violations)
            self.db.update_job_progress(job_id, progress_pct=8, progress_message='Ensuring stocks exist in database...')
            self.db.ensure_stocks_exist_batch(market_data_cache)
            
            # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
            all_symbols = list(market_data_cache.keys())
            
            # Sort by screening score if available (prioritize STRONG_BUY stocks)
            scored_symbols = self.db.get_stocks_ordered_by_score(limit=None)
            scored_set = set(scored_symbols)
            
            # Put scored symbols first (in score order), then remaining unscored symbols
            sorted_symbols = [s for s in scored_symbols if s in set(all_symbols)]
            remaining = [s for s in all_symbols if s not in scored_set]
            all_symbols = sorted_symbols + remaining
        
        # Apply limit if specified
        if limit and limit < len(all_symbols):
            all_symbols = all_symbols[:limit]
        
        total = len(all_symbols)
        logger.info(f"Caching outlook data for {total} stocks (region={region}, sorted by score)")
        
        self.db.update_job_progress(job_id, progress_pct=10,
                                    progress_message=f'Caching outlook for {total} stocks...',
                                    total_count=total)
        
        processed = 0
        cached = 0
        errors = 0
        
        # Process stocks - use moderate parallelism since we're hitting yfinance
        BATCH_SIZE = 20
        MAX_WORKERS = 8
        
        def fetch_outlook_data(symbol: str) -> bool:
            """Fetch forward metrics and insider trades for a single symbol."""
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info
                
                if not info:
                    return False
                
                # Extract forward metrics
                forward_pe = info.get('forwardPE')
                forward_peg = info.get('pegRatio') or info.get('trailingPegRatio')
                forward_eps = info.get('forwardEps')
                
                # Fetch insider transactions
                insider_df = ticker.insider_transactions
                one_year_ago = datetime.now() - timedelta(days=365)
                net_buying = 0.0
                trades_to_save = []
                
                if insider_df is not None and not insider_df.empty:
                    date_col = 'Start Date' if 'Start Date' in insider_df.columns else 'Date'
                    
                    if date_col in insider_df.columns:
                        insider_df[date_col] = pd.to_datetime(insider_df[date_col])
                        
                        for _, row in insider_df.iterrows():
                            t_date = row[date_col]
                            if pd.isna(t_date):
                                continue
                            
                            is_recent = t_date >= one_year_ago
                            
                            text = str(row.get('Text', '')).lower()
                            if 'purchase' in text:
                                transaction_type = 'Buy'
                            elif 'sale' in text:
                                transaction_type = 'Sell'
                            else:
                                transaction_type = 'Other'
                            
                            value = row.get('Value')
                            if pd.isna(value):
                                value = 0.0
                            
                            shares = row.get('Shares')
                            if pd.isna(shares):
                                shares = 0
                            
                            # Calculate net buying for recent transactions
                            if is_recent:
                                if transaction_type == 'Buy':
                                    net_buying += value
                                elif transaction_type == 'Sell':
                                    net_buying -= value
                            
                            trades_to_save.append({
                                'name': row.get('Insider', 'Unknown'),
                                'position': row.get('Position', 'Unknown'),
                                'transaction_date': t_date.strftime('%Y-%m-%d'),
                                'transaction_type': transaction_type,
                                'shares': float(shares),
                                'value': float(value),
                                'filing_url': row.get('URL', '')
                            })
                
                # Extract analyst data
                analyst_rating = info.get('recommendationKey')  # e.g., "buy", "hold", "sell"
                analyst_rating_score = info.get('recommendationMean')  # 1.0 (Strong Buy) to 5.0 (Sell)
                analyst_count = info.get('numberOfAnalystOpinions')
                price_target_high = info.get('targetHighPrice')
                price_target_low = info.get('targetLowPrice')
                price_target_mean = info.get('targetMeanPrice')
                
                # Extract short interest data
                short_ratio = info.get('shortRatio')  # Days to cover
                short_percent_float = info.get('shortPercentOfFloat')
                
                # Extract next earnings date from calendar
                next_earnings_date = None
                try:
                    calendar = ticker.calendar
                    if calendar and 'Earnings Date' in calendar:
                        earnings_dates = calendar['Earnings Date']
                        if earnings_dates and len(earnings_dates) > 0:
                            next_earnings_date = earnings_dates[0]  # First date is next earnings
                except Exception:
                    pass  # Calendar not available for all stocks
                
                # Extract analyst estimates (EPS and Revenue forecasts)
                estimates_data = {}
                try:
                    # EPS estimates (period: 0q, +1q, 0y, +1y)
                    eps_df = ticker.earnings_estimate
                    if eps_df is not None and not eps_df.empty:
                        for period in eps_df.index:
                            row = eps_df.loc[period]
                            if period not in estimates_data:
                                estimates_data[period] = {}
                            estimates_data[period].update({
                                'eps_avg': float(row.get('avg')) if pd.notna(row.get('avg')) else None,
                                'eps_low': float(row.get('low')) if pd.notna(row.get('low')) else None,
                                'eps_high': float(row.get('high')) if pd.notna(row.get('high')) else None,
                                'eps_growth': float(row.get('growth')) if pd.notna(row.get('growth')) else None,
                                'eps_year_ago': float(row.get('yearAgoEps')) if pd.notna(row.get('yearAgoEps')) else None,
                                'eps_num_analysts': int(row.get('numberOfAnalysts')) if pd.notna(row.get('numberOfAnalysts')) else None,
                            })
                    
                    # Revenue estimates
                    rev_df = ticker.revenue_estimate
                    if rev_df is not None and not rev_df.empty:
                        for period in rev_df.index:
                            row = rev_df.loc[period]
                            if period not in estimates_data:
                                estimates_data[period] = {}
                            estimates_data[period].update({
                                'revenue_avg': float(row.get('avg')) if pd.notna(row.get('avg')) else None,
                                'revenue_low': float(row.get('low')) if pd.notna(row.get('low')) else None,
                                'revenue_high': float(row.get('high')) if pd.notna(row.get('high')) else None,
                                'revenue_growth': float(row.get('growth')) if pd.notna(row.get('growth')) else None,
                                'revenue_year_ago': float(row.get('yearAgoRevenue')) if pd.notna(row.get('yearAgoRevenue')) else None,
                                'revenue_num_analysts': int(row.get('numberOfAnalysts')) if pd.notna(row.get('numberOfAnalysts')) else None,
                            })
                except Exception as e:
                    logger.debug(f"[{symbol}] Error extracting analyst estimates: {e}")
                
                # Save to database
                # Update metrics with forward indicators + analyst data
                metrics = {
                    'forward_pe': forward_pe,
                    'forward_peg_ratio': forward_peg,
                    'forward_eps': forward_eps,
                    'insider_net_buying_6m': net_buying,  # Column name kept for compatibility
                    'analyst_rating': analyst_rating,
                    'analyst_rating_score': analyst_rating_score,
                    'analyst_count': analyst_count,
                    'price_target_high': price_target_high,
                    'price_target_low': price_target_low,
                    'price_target_mean': price_target_mean,
                    'short_ratio': short_ratio,
                    'short_percent_float': short_percent_float,
                    'next_earnings_date': next_earnings_date
                }
                
                # Get existing metrics and merge
                existing = self.db.get_stock_metrics(symbol)
                if existing:
                    existing.update({k: v for k, v in metrics.items() if v is not None})
                    self.db.save_stock_metrics(symbol, existing)
                
                # Save insider trades
                if trades_to_save:
                    self.db.save_insider_trades(symbol, trades_to_save)
                
                # Save analyst estimates to the new table
                if estimates_data:
                    self.db.save_analyst_estimates(symbol, estimates_data)
                
                return True
                
            except Exception as e:
                logger.debug(f"[{symbol}] Outlook fetch error: {e}")
                return False
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for batch_start in range(0, total, BATCH_SIZE):
                if self.shutdown_requested:
                    logger.info("Shutdown requested, stopping outlook cache job")
                    break
                
                # Check if job was cancelled
                job_status = self.db.get_background_job(job_id)
                if job_status and job_status.get('status') == 'cancelled':
                    logger.info(f"Job {job_id} was cancelled, stopping")
                    return
                
                batch_end = min(batch_start + BATCH_SIZE, total)
                batch = all_symbols[batch_start:batch_end]
                
                futures = {executor.submit(fetch_outlook_data, symbol): symbol for symbol in batch}
                
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        success = future.result()
                        if success:
                            cached += 1
                        else:
                            errors += 1
                    except Exception as e:
                        logger.debug(f"[{symbol}] Outlook cache error: {e}")
                        errors += 1
                    processed += 1
                
                # Update progress
                if processed % 50 == 0 or batch_end == total:
                    pct = 10 + int((processed / total) * 85)
                    self.db.update_job_progress(
                        job_id,
                        progress_pct=pct,
                        progress_message=f'Cached {processed}/{total} stocks ({cached} successful, {errors} errors)',
                        processed_count=processed,
                        total_count=total
                    )
                    self._send_heartbeat(job_id)
                    logger.info(f"Outlook cache progress: {processed}/{total} (cached: {cached}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                    check_memory_warning(f"[outlook {processed}/{total}]")
                
                # Small delay between batches to avoid rate limiting
                time.sleep(0.5)
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"Outlook cache complete: {result}")

    def _run_transcript_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache earnings call transcripts for all stocks via MarketBeat scraping.
        
        Uses TradingView to get stock list (same as screening/prices) with region filtering.
        Symbols are sorted by score (STRONG_BUY first) when available.
        Skips stocks that already have transcripts cached (unless force_refresh is True).
        
        Params:
            limit: Optional max number of stocks to process
            symbols: Optional list of specific symbols to process (overrides limit)
            region: Region filter (us, north-america, europe, asia, all)
            force_refresh: If True, bypass cache and fetch fresh data
        """
        limit = params.get('limit')
        symbols_list = params.get('symbols')  # For testing specific stocks
        region = params.get('region', 'us')
        force_refresh = params.get('force_refresh', False)
        
        logger.info(f"Starting transcript cache job {job_id} (region={region}, force={force_refresh})")
        
        from transcript_scraper import TranscriptScraper
        from tradingview_fetcher import TradingViewFetcher
        
        # If specific symbols provided, use those directly
        if symbols_list:
            all_symbols = symbols_list if isinstance(symbols_list, list) else [symbols_list]
            logger.info(f"Processing specific symbols: {all_symbols}")
        else:
            # Map CLI region to TradingView regions (same as other cache jobs)
            region_mapping = {
                'us': ['us'],
                'north-america': ['north_america'],
                'south-america': ['south_america'],
                'europe': ['europe'],
                'asia': ['asia'],
                'all': None  # All regions
            }
            tv_regions = region_mapping.get(region, ['us'])
            
            # Get stock list from TradingView (same as prices/news does)
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
            tv_fetcher = TradingViewFetcher()
            market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
            
            # Ensure all stocks exist in DB before caching (prevents FK violations)
            self.db.update_job_progress(job_id, progress_pct=8, progress_message='Ensuring stocks exist in database...')
            self.db.ensure_stocks_exist_batch(market_data_cache)
            
            # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
            all_symbols = list(market_data_cache.keys())
            
            # Sort by screening score if available (prioritize STRONG_BUY stocks)
            scored_symbols = self.db.get_stocks_ordered_by_score(limit=None)
            scored_set = set(scored_symbols)
            
            # Put scored symbols first (in score order), then remaining unscored symbols
            sorted_symbols = [s for s in scored_symbols if s in set(all_symbols)]
            remaining = [s for s in all_symbols if s not in scored_set]
            all_symbols = sorted_symbols + remaining
            
            # Apply limit if specified
            if limit and limit < len(all_symbols):
                all_symbols = all_symbols[:limit]
        
        total = len(all_symbols)
        logger.info(f"Caching transcripts for {total} stocks (region={region}, sorted by score)")
        
        self.db.update_job_progress(job_id, progress_pct=10,
                                    progress_message=f'Caching transcripts for {total} stocks...',
                                    processed_count=0,
                                    total_count=total)
        
        # Initialize scraper (Playwright session) - runs async
        processed = 0
        cached = 0
        skipped = 0
        errors = 0
        
        # Pre-compute skip list BEFORE entering async context to avoid blocking DB calls
        # This keeps all synchronous DB work outside the async function
        skip_set = set()
        if not force_refresh:
            logger.info("Pre-computing skip list for existing transcripts...")
            for symbol in all_symbols:
                try:
                    existing = self.db.get_latest_earnings_transcript(symbol)
                    if existing and existing.get('transcript_text'):
                        skip_set.add(symbol)
                except Exception as e:
                    logger.debug(f"[{symbol}] Skip check error: {e}")
            logger.info(f"Will skip {len(skip_set)} stocks with existing transcripts")
        
        async def run_transcript_caching():
            nonlocal processed, cached, skipped, errors
            
            logger.info("Starting async transcript scraper...")
            async with TranscriptScraper() as scraper:
                logger.info("Browser started successfully")
                
                for symbol in all_symbols:
                    logger.info(f"[{symbol}] Processing...")
                    
                    # Check for shutdown/cancellation
                    if self.shutdown_requested:
                        logger.info("Shutdown requested, stopping transcript cache job")
                        break
                    
                    # Check if job was cancelled
                    job_status = self.db.get_background_job(job_id)
                    if job_status and job_status.get('status') == 'cancelled':
                        logger.info(f"Job {job_id} was cancelled, stopping")
                        break
                    
                    # Skip if already cached (using pre-computed set)
                    if symbol in skip_set:
                        skipped += 1
                        processed += 1
                        if processed % 50 == 0:
                            logger.info(f"Transcript cache progress: {processed}/{total} (cached: {cached}, skipped: {skipped}, errors: {errors})")
                        continue
                    
                    try:
                        logger.info(f"[{symbol}] Fetching transcript from MarketBeat...")
                        # Add 90 second timeout per stock to prevent infinite hangs
                        import asyncio
                        result = await asyncio.wait_for(
                            scraper.fetch_latest_transcript(symbol),
                            timeout=90.0
                        )
                        if result:
                            logger.info(f"[{symbol}] Saving transcript ({len(result.get('transcript_text', ''))} chars)...")
                            self.db.save_earnings_transcript(symbol, result)
                            cached += 1
                            logger.info(f"[{symbol}] Cached transcript successfully")
                        else:
                            # Save a marker record with "NO_TRANSCRIPT" so we skip this stock in future runs
                            logger.info(f"[{symbol}] No transcript available - saving marker to skip in future")
                            self.db.save_earnings_transcript(symbol, {
                                'quarter': 'N/A',
                                'fiscal_year': 0,
                                'transcript_text': 'NO_TRANSCRIPT_AVAILABLE',
                                'has_qa': False,
                                'participants': [],
                                'source_url': ''
                            })
                            skipped += 1
                    except asyncio.TimeoutError:
                        logger.warning(f"[{symbol}] Transcript fetch TIMED OUT after 90s - skipping")
                        errors += 1
                    except Exception as e:
                        logger.warning(f"[{symbol}] Transcript cache error: {e}")
                        errors += 1
                    
                    processed += 1
                    
                    # Update progress every 25 stocks
                    if processed % 25 == 0 or processed == total:
                        pct = 10 + int((processed / total) * 85)
                        self.db.update_job_progress(
                            job_id,
                            progress_pct=pct,
                            progress_message=f'Cached {processed}/{total} stocks ({cached} new, {skipped} skipped, {errors} errors)',
                            processed_count=processed,
                            total_count=total
                        )
                        self._send_heartbeat(job_id)
                    
                    if processed % 50 == 0:
                        logger.info(f"Transcript cache progress: {processed}/{total} (cached: {cached}, skipped: {skipped}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                        check_memory_warning(f"[transcript {processed}/{total}]")
        
        # Run the async caching function
        logger.info("Running async transcript caching...")
        import asyncio
        asyncio.run(run_transcript_caching())
        logger.info("Async transcript caching completed")
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'skipped': skipped,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"Transcript cache complete: {result}")


def main():
    """Entry point for worker process"""
    logger.info("=" * 60)
    logger.info("Lynch Stock Screener - Background Worker")
    logger.info("=" * 60)
    
    # Configure global SEC rate limiter
    configure_edgartools_rate_limit()
    logger.info(f"SEC Rate Limiter: {SEC_RATE_LIMITER.get_stats()}")

    worker = BackgroundWorker()
    worker.run()


if __name__ == '__main__':
    main()
