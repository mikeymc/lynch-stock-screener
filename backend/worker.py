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

        results = []
        processed_count = 0
        failed_symbols = []

        BATCH_SIZE = 10
        MAX_WORKERS = 40
        BATCH_DELAY = 0.5

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
                            results.append(evaluation)
                        else:
                            failed_symbols.append(symbol)
                    except Exception as e:
                        logger.error(f"Error getting result for {symbol}: {e}")
                        failed_symbols.append(symbol)

                # Update progress
                progress_pct = 15 + int((processed_count / total) * 80)  # 15-95%
                self.db.update_job_progress(job_id, progress_pct=progress_pct,
                                            progress_message=f'Processed {processed_count}/{total}',
                                            processed_count=processed_count)
                
                logger.info(f"========== SCREENING PROGRESS: {processed_count}/{total} ({progress_pct}%) | MEMORY: {get_memory_mb():.0f}MB ==========")
                
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
                        results.append(evaluation)
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Retry error for {symbol}: {e}")

        # Calculate final counts
        if algorithm == 'classic':
            pass_count = len([r for r in results if r['overall_status'] == 'PASS'])
            close_count = len([r for r in results if r['overall_status'] == 'CLOSE'])
            fail_count = len([r for r in results if r['overall_status'] == 'FAIL'])
        else:
            pass_count = len([r for r in results if r['overall_status'] in ['STRONG_BUY', 'BUY']])
            close_count = len([r for r in results if r['overall_status'] == 'HOLD'])
            fail_count = len([r for r in results if r['overall_status'] in ['CAUTION', 'AVOID']])

        total_analyzed = len(results)

        # Complete session if we have one
        if session_id:
            self.db.complete_session(session_id, total_analyzed, pass_count, close_count, fail_count)

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
        
        # TradingView already filters via _should_skip_ticker (OTC, warrants, etc.)
        all_symbols = list(market_data_cache.keys())
        
        # Apply limit if specified
        if limit and limit < len(all_symbols):
            all_symbols = all_symbols[:limit]
        
        total = len(all_symbols)
        logger.info(f"Caching price history for {total} stocks (ordered by score)")
        
        self.db.update_job_progress(job_id, progress_pct=10, 
                                    progress_message=f'Caching price history for {total} stocks...',
                                    total_count=total)
        
        # Initialize fetchers
        price_client = YFinancePriceClient()
        # Note: Rate limiting is handled by global YFINANCE_SEMAPHORE in yfinance_rate_limiter.py
        price_history_fetcher = PriceHistoryFetcher(self.db, price_client, yf_semaphore=None)
        
        processed = 0
        cached = 0
        errors = 0
        
        # Process in batches with threading for performance
        BATCH_SIZE = 50
        MAX_WORKERS = 12
        
        for batch_start in range(0, total, BATCH_SIZE):
            if self.shutdown_requested:
                logger.info("Shutdown requested, stopping price history cache job")
                break
            
            # Check if job was cancelled
            job_status = self.db.get_background_job(job_id)
            if job_status and job_status.get('status') == 'cancelled':
                logger.info(f"Job {job_id} was cancelled, stopping")
                return
            
            batch_end = min(batch_start + BATCH_SIZE, total)
            batch = all_symbols[batch_start:batch_end]
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(price_history_fetcher.fetch_and_cache_prices, symbol): symbol for symbol in batch}
                
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        future.result()
                        cached += 1
                    except Exception as e:
                        logger.debug(f"[{symbol}] Price history cache error: {e}")
                        errors += 1
                    processed += 1
            
            # Update progress
            if processed % 100 == 0 or batch_end == total:
                pct = 10 + int((processed / total) * 85)
                self.db.update_job_progress(
                    job_id, 
                    progress_pct=pct,
                    progress_message=f'Cached {processed}/{total} stocks ({cached} successful, {errors} errors)',
                    processed_count=processed,
                    total_count=total
                )
                self._send_heartbeat(job_id)
                logger.info(f"Price history cache progress: {processed}/{total} (cached: {cached}, errors: {errors})")
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"Price history cache complete: {result}")

    def _run_news_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache news articles for all stocks via Finnhub.
        
        Orders stocks by overall_score (STRONG_BUY first) to prioritize the best stocks.
        Uses database for stock list (only caches for stocks we actually have).
        
        Params:
            limit: Optional max number of stocks to process
        """
        limit = params.get('limit')
        
        logger.info(f"Starting news cache job {job_id}")
        
        from finnhub_news import FinnhubNewsClient
        
        # Get stocks ordered by score (from DB - ensures FK constraint is satisfied)
        self.db.update_job_progress(job_id, progress_pct=5, progress_message='Loading stock list by priority...')
        all_symbols = self.db.get_stocks_ordered_by_score(limit=limit)
        
        total = len(all_symbols)
        logger.info(f"Caching news for {total} stocks (ordered by score)")
        
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
                logger.info(f"News cache progress: {processed}/{total} (cached: {cached}, errors: {errors})")
        
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
        
        Orders stocks by overall_score (STRONG_BUY first) to prioritize the best stocks.
        Sequential processing due to SEC rate limits.
        
        Params:
            limit: Optional max number of stocks to process
            force_refresh: If True, bypass cache and fetch fresh data
        """
        limit = params.get('limit')
        force_refresh = params.get('force_refresh', False)
        
        logger.info(f"Starting 10-K/10-Q cache job {job_id}")
        
        from edgar_fetcher import EdgarFetcher
        
        # Get stocks ordered by score
        self.db.update_job_progress(job_id, progress_pct=5, progress_message='Loading stock list by priority...')
        all_symbols = self.db.get_stocks_ordered_by_score(limit=limit)
        
        total = len(all_symbols)
        logger.info(f"Caching 10-K/10-Q for {total} stocks (ordered by score)")
        
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
            
            if processed % 100 == 0:
                logger.info(f"10-K/10-Q cache progress: {processed}/{total} (cached: {cached}, errors: {errors})")
        
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
        
        Orders stocks by overall_score (STRONG_BUY first) to prioritize the best stocks.
        Sequential processing due to SEC rate limits.
        
        Params:
            limit: Optional max number of stocks to process
            force_refresh: If True, bypass cache and fetch fresh data
        """
        limit = params.get('limit')
        force_refresh = params.get('force_refresh', False)
        
        logger.info(f"Starting 8-K cache job {job_id}")
        
        from edgar_fetcher import EdgarFetcher
        from sec_8k_client import SEC8KClient
        
        # Get stocks ordered by score
        self.db.update_job_progress(job_id, progress_pct=5, progress_message='Loading stock list by priority...')
        all_symbols = self.db.get_stocks_ordered_by_score(limit=limit)
        
        total = len(all_symbols)
        logger.info(f"Caching 8-K events for {total} stocks (ordered by score)")
        
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
            
            if processed % 100 == 0:
                logger.info(f"8-K cache progress: {processed}/{total} (cached: {cached}, errors: {errors})")
        
        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'errors': errors
        }
        self.db.complete_job(job_id, result)
        logger.info(f"8-K cache complete: {result}")


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
