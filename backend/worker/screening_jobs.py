# ABOUTME: Stock screening job mixin for the background worker
# ABOUTME: Handles full stock screening with parallel data fetching

import time
import logging
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class ScreeningJobsMixin:
    """Mixin for the full_screening job type"""

    def _run_screening(self, job_id: int, params: Dict[str, Any]):
        """Execute full stock screening"""
        from worker.core import get_memory_mb, check_memory_warning

        algorithm = params.get('algorithm', 'weighted')
        force_refresh = params.get('force_refresh', False)
        limit = params.get('limit')
        region = params.get('region', 'us')  # Default to US only
        specific_symbols = params.get('symbols')  # Optional list of specific symbols to screen

        from tradingview_fetcher import TradingViewFetcher
        from finviz_fetcher import FinvizFetcher
        from data_fetcher import DataFetcher

        # Initialize fetcher (no longer need criteria/analyzer since we don't score)
        fetcher = DataFetcher(self.db)

        # If specific symbols provided, use those directly (for testing)
        if specific_symbols:
            logger.info(f"Screening specific symbols: {specific_symbols}")
            self.db.update_job_progress(job_id, progress_pct=10, progress_message=f'Screening {len(specific_symbols)} specific symbols...')

            # Skip bulk TradingView/Finviz fetches - let fetch_stock_data handle each symbol individually
            filtered_symbols = specific_symbols
            market_data_cache = {}  # Empty cache = each symbol fetches its own data
            finviz_cache = {}
        else:
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

        logger.info(f"Ready to screen {total} stocks")

        # Process stocks
        def process_stock(symbol):
            try:
                # Fetch stock data (character-independent - just raw fundamentals)
                stock_data = fetcher.fetch_stock_data(symbol, force_refresh,
                                                      market_data_cache=market_data_cache,
                                                      finviz_cache=finviz_cache)
                if not stock_data:
                    return None

                # NOTE: Scoring is now done on-demand via /api/sessions/latest
                # This screening job only fetches and caches raw data
                # Price history and news caching are handled by separate jobs:
                # - price_history_cache: Caches weekly price history
                # - news_cache: Caches Finnhub news articles
                # - 10k_cache: Caches 10-K/10-Q sections
                # - 8k_cache: Caches 8-K material events

                return {'symbol': symbol, 'success': True}

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                return None

        # Initialize counters (no longer tracking pass/close/fail since we don't score)
        total_analyzed = 0
        processed_count = 0
        failed_symbols = []

        BATCH_SIZE = 10
        MAX_WORKERS = 8  # Reduced from 20 to prevent DB pool exhaustion
        BATCH_DELAY = 1.0 # Increased from 0.5 to reduce write pressure

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
                        result = future.result()
                        if result and result.get('success'):
                            total_analyzed += 1
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

                pool_stats = self.db.get_pool_stats()
                logger.info(f"========== SCREENING PROGRESS: {processed_count}/{total} ({progress_pct}%) | MEMORY: {get_memory_mb():.0f}MB | DB POOL: {pool_stats['current_in_use']}/{pool_stats['pool_size']} (peak: {pool_stats['peak_in_use']}) ==========")
                check_memory_warning(f"[screening {processed_count}/{total}]")

                # Periodic garbage collection to prevent memory buildup

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
                    result = process_stock(symbol)
                    if result and result.get('success'):
                        total_analyzed += 1

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
            'total_symbols': total,
            'failed_count': len(failed_symbols)
        }
        # Flush write queue before completing job
        self.db.flush()
        self.db.complete_job(job_id, result)
        logger.info(f"Screening complete: {total_analyzed} stocks analyzed")
