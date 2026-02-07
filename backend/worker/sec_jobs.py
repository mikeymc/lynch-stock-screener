# ABOUTME: SEC filing cache job mixins for the background worker
# ABOUTME: Handles SEC refresh, 10-K/10-Q caching, 8-K material events, and Form 4 insider filings

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from sec_data_fetcher import SECDataFetcher
from material_events_fetcher import MaterialEventsFetcher

logger = logging.getLogger(__name__)


class SECJobsMixin:
    """Mixin for SEC-related jobs: sec_refresh, 10k_cache, 8k_cache, form4_cache"""

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
        from worker.core import get_memory_mb, check_memory_warning

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

            # Get tickers with new 10-K OR 10-Q filings from RSS (with pagination)
            known_tickers = set(all_symbols)
            tickers_10k = rss_client.get_tickers_with_new_filings_paginated('10-K', known_tickers=known_tickers, db=self.db)
            tickers_10q = rss_client.get_tickers_with_new_filings_paginated('10-Q', known_tickers=known_tickers, db=self.db)
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
        # Flush write queue before completing job
        self.db.flush()
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
            symbols: Optional list of specific symbols to process (for testing)
            use_rss: If True, use RSS feed to pre-filter to only stocks with new filings
        """
        from worker.core import get_memory_mb, check_memory_warning

        limit = params.get('limit')
        region = params.get('region', 'us')
        force_refresh = params.get('force_refresh', False)
        specific_symbols = params.get('symbols')  # Optional list of specific symbols
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
            self.db.update_job_progress(job_id, progress_pct=9, progress_message='Checking RSS feed for new 8-K filings...')

            sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
            rss_client = SECRSSClient(sec_user_agent)

            # Get tickers with new 8-K filings from RSS (with pagination)
            known_tickers = set(all_symbols)
            tickers_with_filings = rss_client.get_tickers_with_new_filings_paginated('8-K', known_tickers=known_tickers, db=self.db)

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
        events_fetcher = MaterialEventsFetcher(self.db, sec_8k_client, data_fetcher=self.data_fetcher)

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
        # Flush write queue before completing job
        self.db.flush()
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
        from worker.core import get_memory_mb, check_memory_warning

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

            # Get tickers with new Form 4 filings from RSS (with pagination)
            known_tickers = set(all_symbols)
            tickers_with_filings = rss_client.get_tickers_with_new_filings_paginated('FORM4', known_tickers=known_tickers, db=self.db)

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

            # Flush write queue every 100 symbols (non-blocking)
            if processed % 100 == 0:
                self.db.flush_async()

        # Final flush to ensure all queued writes are committed
        self.db.flush()

        # Complete job
        result = {
            'total_stocks': total,
            'processed': processed,
            'cached': cached,
            'skipped': skipped,
            'total_transactions': total_transactions,
            'errors': errors
        }
        # Flush write queue before completing job
        self.db.flush()
        self.db.complete_job(job_id, result)
        logger.info(f"Form 4 cache complete: {result}")
