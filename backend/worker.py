# ABOUTME: Background worker process for executing long-running jobs
# ABOUTME: Polls PostgreSQL for jobs, executes screening and SEC refresh tasks

import os
import sys
import time
import signal
import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Dict, Any

# Import fetcher modules for data caching
from price_history_fetcher import PriceHistoryFetcher
from sec_data_fetcher import SECDataFetcher
from news_fetcher import NewsFetcher
from material_events_fetcher import MaterialEventsFetcher

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
IDLE_SHUTDOWN_SECONDS = int(os.environ.get('WORKER_IDLE_TIMEOUT', 300))  # 5 minutes
HEARTBEAT_INTERVAL = 60  # Extend claim every 60 seconds
POLL_INTERVAL = 5  # Check for new jobs every 5 seconds


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
        logger.info(f"Idle shutdown: {IDLE_SHUTDOWN_SECONDS}s, Poll interval: {POLL_INTERVAL}s")

        while not self.shutdown_requested:
            # Check for idle shutdown
            idle_time = time.time() - self.last_job_time
            if idle_time > IDLE_SHUTDOWN_SECONDS:
                logger.info(f"Idle for {idle_time:.0f}s (limit: {IDLE_SHUTDOWN_SECONDS}s), shutting down")
                break

            # Try to claim a job
            job = self.db.claim_pending_job(self.worker_id)

            if job:
                self.current_job_id = job['id']
                self.last_job_time = time.time()
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

        logger.info(f"Starting screening (session_id={session_id}, algorithm={algorithm}, force_refresh={force_refresh}, limit={limit})")

        # Import dependencies
        from data_fetcher import DataFetcher
        from lynch_criteria import LynchCriteria
        from earnings_analyzer import EarningsAnalyzer
        from tradingview_fetcher import TradingViewFetcher
        from tradingview_price_client import TradingViewPriceClient
        from finviz_fetcher import FinvizFetcher
        from edgar_fetcher import EdgarFetcher
        from finnhub_news import FinnhubNewsClient
        from sec_8k_client import SEC8KClient
        
        # Initialize fetchers
        fetcher = DataFetcher(self.db)
        analyzer = EarningsAnalyzer(self.db)
        edgar_fetcher = EdgarFetcher(
            user_agent="Lynch Stock Screener mikey@example.com",
            db=self.db
        )
        finnhub_client = FinnhubNewsClient(api_key=os.environ.get('FINNHUB_API_KEY', 'd4nkaqpr01qk2nucd6q0d4nkaqpr01qk2nucd6qg'))
        sec_8k_client = SEC8KClient(user_agent=os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com'))
        
        # Initialize price client
        price_client = TradingViewPriceClient()
        
        # Initialize fetchers for data caching
        price_history_fetcher = PriceHistoryFetcher(self.db, price_client)
        sec_data_fetcher = SECDataFetcher(self.db, edgar_fetcher)
        news_fetcher_instance = NewsFetcher(self.db, finnhub_client)
        events_fetcher = MaterialEventsFetcher(self.db, sec_8k_client)
        criteria = LynchCriteria(self.db, analyzer)

        # Bulk prefetch market data
        self.db.update_job_progress(job_id, progress_pct=5, progress_message='Fetching market data from TradingView...')
        tv_fetcher = TradingViewFetcher()
        market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000)
        logger.info(f"Loaded {len(market_data_cache)} stocks from TradingView")

        self._send_heartbeat(job_id)

        # Bulk prefetch institutional ownership
        self.db.update_job_progress(job_id, progress_pct=10, progress_message='Fetching institutional ownership from Finviz...')
        finviz_fetcher = FinvizFetcher()
        finviz_cache = finviz_fetcher.fetch_all_institutional_ownership(limit=20000)
        logger.info(f"Loaded {len(finviz_cache)} institutional ownership values from Finviz")

        self._send_heartbeat(job_id)

        # Filter and prepare symbols
        tv_symbols = list(market_data_cache.keys())
        filtered_symbols = []
        for sym in tv_symbols:
            if any(char in sym for char in ['$', '-', '.']) and sym not in ['BRK.B', 'BF.B']:
                continue
            if len(sym) >= 5 and sym[-1] in ['W', 'R', 'U']:
                continue
            filtered_symbols.append(sym)

        # Apply limit if specified
        if limit and limit < len(filtered_symbols):
            filtered_symbols = filtered_symbols[:limit]

        total = len(filtered_symbols)
        self.db.update_job_progress(job_id, progress_pct=15, progress_message=f'Screening {total} stocks...',
                                    total_count=total)

        # Update session total count if we have a session
        if session_id:
            self.db.update_session_total_count(session_id, total)

        logger.info(f"Ready to screen {total} stocks")

        # Process stocks
        def process_stock(symbol):
            try:
                # 1. Fetch stock data (existing)
                stock_data = fetcher.fetch_stock_data(symbol, force_refresh,
                                                      market_data_cache=market_data_cache,
                                                      finviz_cache=finviz_cache)
                if not stock_data:
                    return None

                # 2. Evaluate stock (existing)
                evaluation = criteria.evaluate_stock(symbol, algorithm=algorithm)
                if not evaluation:
                    return None

                # 3. NEW: Fetch and cache all external data IN PARALLEL
                with ThreadPoolExecutor(max_workers=4) as data_executor:
                    # Submit all fetches concurrently
                    data_futures = {
                        data_executor.submit(price_history_fetcher.fetch_and_cache_prices, symbol): 'prices',
                        data_executor.submit(sec_data_fetcher.fetch_and_cache_all, symbol): 'sec',
                        data_executor.submit(news_fetcher_instance.fetch_and_cache_news, symbol): 'news',
                        data_executor.submit(events_fetcher.fetch_and_cache_events, symbol): 'events'
                    }
                    
                    # Wait for all to complete (with timeout)
                    for future in as_completed(data_futures, timeout=10):
                        data_type = data_futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            # Log but don't fail the stock - data caching is optional
                            logger.debug(f"[{symbol}] Failed to cache {data_type}: {e}")

                # 4. Save screening result (existing)
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


def main():
    """Entry point for worker process"""
    logger.info("=" * 60)
    logger.info("Lynch Stock Screener - Background Worker")
    logger.info("=" * 60)

    worker = BackgroundWorker()
    worker.run()


if __name__ == '__main__':
    main()
