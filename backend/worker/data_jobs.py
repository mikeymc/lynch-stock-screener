# ABOUTME: Data caching job mixins for the background worker
# ABOUTME: Handles historical fundamentals, quarterly fundamentals, price updates, price history, and dividends

import os
import time
import logging
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class DataJobsMixin:
    """Mixin for data caching jobs: fundamentals, prices, dividends"""

    def _run_historical_fundamentals_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cold storage job: Fetch >2 year historical fundamental data via company_facts API.

        This job runs infrequently (quarterly) to populate historical earnings_history data.
        It fetches ONLY from company_facts (not 10-Q filings), storing data older than 2 years.

        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            symbols: Optional list of specific symbols to process
            force_refresh: If True, re-fetch even if historical data exists
        """
        limit = params.get('limit')
        region = params.get('region', 'us')
        specific_symbols = params.get('symbols')
        force_refresh = params.get('force_refresh', False)

        logger.info(f"Starting historical_fundamentals_cache job {job_id} (region={region})")

        from tradingview_fetcher import TradingViewFetcher
        from edgar_fetcher import EdgarFetcher

        # Get stock list
        if specific_symbols:
            all_symbols = specific_symbols
            logger.info(f"Processing specific symbols: {all_symbols}")
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Processing {len(all_symbols)} specific symbols...')
        else:
            region_mapping = {
                'us': ['us'],
                'north-america': ['north_america'],
                'south-america': ['south_america'],
                'europe': ['europe'],
                'asia': ['asia'],
                'all': None
            }
            tv_regions = region_mapping.get(region, ['us'])

            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
            tv_fetcher = TradingViewFetcher()
            market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
            all_symbols = list(market_data_cache.keys())

            if limit and limit < len(all_symbols):
                all_symbols = all_symbols[:limit]

        total = len(all_symbols)
        self.db.update_job_progress(job_id, progress_pct=10, progress_message=f'Caching historical data for {total} stocks...',
                                    total_count=total)

        logger.info(f"Processing {total} stocks for historical fundamentals")

        sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
        edgar_fetcher = EdgarFetcher(user_agent=sec_user_agent, db=self.db)

        def process_stock(symbol):
            try:
                # Check if we already have historical data (skip if not force_refresh)
                if not force_refresh:
                    annual_rows = self.db.get_earnings_history(symbol, period_type='annual')
                    if annual_rows and len(annual_rows) >= 5:
                        logger.info(f"[{symbol}] Already has {len(annual_rows)} years of historical data - skipping")
                        return {'symbol': symbol, 'status': 'cached'}

                # Get CIK
                cik = edgar_fetcher.get_cik_for_ticker(symbol)
                if not cik:
                    logger.warning(f"[{symbol}] CIK not found in SEC mapping - company may be delisted or use different ticker")
                    return {'symbol': symbol, 'status': 'failed', 'reason': 'cik_not_found'}

                # Fetch company_facts (historical data)
                company_facts = edgar_fetcher.fetch_company_facts(cik)
                if not company_facts:
                    logger.warning(f"[{symbol}] No company facts available (CIK: {cik}) - may have no XBRL filings or API error")
                    return {'symbol': symbol, 'status': 'failed', 'reason': 'no_company_facts', 'cik': cik}

                # Parse annual historical data ONLY (skip quarterly - that's handled by quarterly job)
                eps_history = edgar_fetcher.parse_eps_history(company_facts)
                revenue_history = edgar_fetcher.parse_revenue_history(company_facts)
                net_income_annual = edgar_fetcher.parse_net_income_history(company_facts)
                debt_to_equity_history = edgar_fetcher.parse_debt_to_equity_history(company_facts)
                shareholder_equity_history = edgar_fetcher.parse_shareholder_equity_history(company_facts)
                cash_flow_history = edgar_fetcher.parse_cash_flow_history(company_facts)
                cash_equivalents_history = edgar_fetcher.parse_cash_equivalents_history(company_facts)
                shares_outstanding_history = edgar_fetcher.parse_shares_outstanding_history(company_facts)

                # Check if we got any useful data
                if not revenue_history or len(revenue_history) == 0:
                    logger.warning(f"[{symbol}] Company facts returned but no revenue data found (CIK: {cik})")
                    return {'symbol': symbol, 'status': 'failed', 'reason': 'no_revenue_data', 'cik': cik}

                # Store annual data to earnings_history table
                # This uses the same storage logic as the full screening job
                from data_fetcher import DataFetcher
                data_fetcher = DataFetcher(self.db)

                # Create a minimal edgar_data dict with just annual data
                edgar_data = {
                    'eps_history': eps_history,
                    'revenue_history': revenue_history,
                    'net_income_annual': net_income_annual,
                    'debt_to_equity_history': debt_to_equity_history,
                    'shareholder_equity_history': shareholder_equity_history,
                    'cash_flow_history': cash_flow_history,
                    'cash_equivalents_history': cash_equivalents_history,
                    'shares_outstanding_history': shares_outstanding_history,
                }

                # Store to DB (this populates earnings_history table)
                data_fetcher._store_edgar_earnings(symbol, edgar_data, price_history=None)
                
                # CRITICAL: Flush write queue to ensure data is committed
                # Without this, cash_and_cash_equivalents and shares_outstanding won't persist
                self.db.flush()

                logger.info(f"[{symbol}] Cached {len(revenue_history)} years of historical data")
                return {'symbol': symbol, 'status': 'success', 'years': len(revenue_history)}

            except Exception as e:
                logger.error(f"[{symbol}] Unexpected error caching historical data: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                return {'symbol': symbol, 'status': 'failed', 'reason': 'exception', 'error': str(e)}

        # Process stocks with reduced parallelism to avoid DB pressure
        from concurrent.futures import ThreadPoolExecutor
        processed_count = 0
        success_count = 0
        cached_count = 0
        failed_count = 0
        failure_reasons = {}  # Track failure reasons

        BATCH_SIZE = 10
        MAX_WORKERS = 4  # Reduced for heavy company_facts calls

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for i in range(0, total, BATCH_SIZE):
                batch = all_symbols[i:i + BATCH_SIZE]
                futures = {executor.submit(process_stock, symbol): symbol for symbol in batch}

                for future in futures:
                    result = future.result()
                    processed_count += 1

                    if result:
                        status = result.get('status')
                        if status == 'cached':
                            cached_count += 1
                        elif status == 'success':
                            success_count += 1
                        elif status == 'failed':
                            failed_count += 1
                            # Track failure reason
                            reason = result.get('reason', 'unknown')
                            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
                    else:
                        failed_count += 1
                        failure_reasons['unknown'] = failure_reasons.get('unknown', 0) + 1

                    if processed_count % 10 == 0:
                        progress_pct = 10 + int((processed_count / total) * 85)
                        self.db.update_job_progress(
                            job_id,
                            progress_pct=progress_pct,
                            progress_message=f'Processed {processed_count}/{total} stocks (success: {success_count}, cached: {cached_count}, failed: {failed_count})',
                            processed_count=processed_count
                        )
                        self._send_heartbeat(job_id)

        # Complete with detailed failure breakdown
        result_message = f"Historical fundamentals cached: {success_count} new, {cached_count} already cached, {failed_count} failed out of {total} stocks"
        if failure_reasons:
            reason_summary = ", ".join([f"{reason}: {count}" for reason, count in sorted(failure_reasons.items(), key=lambda x: -x[1])])
            result_message += f" | Failure breakdown: {reason_summary}"
        
        self.db.complete_job(job_id, result=result_message)
        logger.info(result_message)

    def _run_quarterly_fundamentals_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Hot data job: Fetch recent quarterly data via 10-Q filing parsing.

        This job runs nightly with smart caching to only fetch new quarters when available.
        It uses edgar_fetcher._needs_quarterly_refresh() to detect stale data.

        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            symbols: Optional list of specific symbols to process
            force_refresh: If True, re-fetch even if quarterly data is current
            use_rss: If True, use RSS feed to pre-filter to only stocks with new filings
        """
        limit = params.get('limit')
        region = params.get('region', 'us')
        specific_symbols = params.get('symbols')
        force_refresh = params.get('force_refresh', False)
        use_rss = params.get('use_rss', True)

        logger.info(f"Starting quarterly_fundamentals_cache job {job_id} (region={region}, use_rss={use_rss})")

        from tradingview_fetcher import TradingViewFetcher
        from edgar_fetcher import EdgarFetcher

        # Get stock list
        if specific_symbols:
            all_symbols = specific_symbols
            logger.info(f"Processing specific symbols: {all_symbols}")
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Processing {len(all_symbols)} specific symbols...')
        else:
            region_mapping = {
                'us': ['us'],
                'north-america': ['north_america'],
                'south-america': ['south_america'],
                'europe': ['europe'],
                'asia': ['asia'],
                'all': None
            }
            tv_regions = region_mapping.get(region, ['us'])

            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
            tv_fetcher = TradingViewFetcher()
            market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)
            all_symbols = list(market_data_cache.keys())

        # RSS-based optimization: only process stocks with new filings
        if use_rss and not force_refresh and not specific_symbols:
            from sec_rss_client import SECRSSClient
            self.db.update_job_progress(job_id, progress_pct=9, progress_message='Checking RSS feed for new 10-Q/10-K filings...')

            sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
            rss_client = SECRSSClient(sec_user_agent)

            # Get tickers with new 10-Q OR 10-K filings from RSS (with pagination)
            known_tickers = set(all_symbols)
            tickers_10q = rss_client.get_tickers_with_new_filings_paginated('10-Q', known_tickers=known_tickers, db=self.db)
            tickers_10k = rss_client.get_tickers_with_new_filings_paginated('10-K', known_tickers=known_tickers, db=self.db)
            tickers_with_filings = tickers_10q | tickers_10k

            if tickers_with_filings:
                # Filter to only stocks with new filings, preserving order
                all_symbols = [s for s in all_symbols if s in tickers_with_filings]
                logger.info(f"RSS optimization: reduced from {len(known_tickers)} to {len(all_symbols)} stocks with new 10-Q/10-K filings")
            else:
                logger.info("RSS optimization: No new 10-Q/10-K filings found today - nothing to update")
                self.db.complete_job(job_id, {'total_stocks': 0, 'processed': 0, 'updated': 0, 'rss_optimized': True})
                return

        total = len(all_symbols)
        self.db.update_job_progress(job_id, progress_pct=10, progress_message=f'Caching quarterly data for {total} stocks...',
                                    total_count=total)

        logger.info(f"Processing {total} stocks for quarterly fundamentals")

        sec_user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener mikey@example.com')
        edgar_fetcher = EdgarFetcher(user_agent=sec_user_agent, db=self.db)

        def process_stock(symbol):
            try:
                from datetime import datetime, timedelta
                # Check if we need to refresh quarterly data (smart caching)
                if not force_refresh:
                    # Check if DB already has the expected data
                    needs_refresh = edgar_fetcher._needs_quarterly_refresh(symbol)
                    if not needs_refresh:
                        logger.info(f"[{symbol}] Quarterly data is current - skipping")
                        return {'symbol': symbol, 'status': 'current'}

                # Record this check in DB even if it fails, to prevent perpetual refresh attempts
                self.db.record_cache_check(symbol, 'quarterly_financials')

                # Fetch quarterly data from 10-Q/10-K filings (last 8 filings)
                quarterly_data = edgar_fetcher.get_quarterly_financials_from_filings(symbol, num_quarters=8)

                if not quarterly_data or not quarterly_data.get('revenue_quarterly'):
                    logger.warning(f"[{symbol}] No quarterly data found in 10-K/10-Q filings")
                    return None

                # Get CIK for URL generation
                cik = edgar_fetcher.get_cik_for_ticker(symbol)

                # Sync filings to DB so RSS client knows we've processed them
                filings_metadata = quarterly_data.get('filings_metadata', [])
                for filing in filings_metadata:
                    self.db.save_sec_filing(
                        symbol, filing['form'], filing['date'],
                        f"https://www.sec.gov/Archives/edgar/data/{cik}/{filing['accession_number'].replace('-', '')}/{filing['accession_number']}-index.html",
                        filing['accession_number']
                    )

                # Store quarterly data to earnings_history table
                from data_fetcher import DataFetcher
                data_fetcher = DataFetcher(self.db)

                # The data is already in the right format for storage
                revenue_quarterly = quarterly_data.get('revenue_quarterly', [])
                net_income_quarterly = quarterly_data.get('net_income_quarterly', [])
                eps_quarterly = quarterly_data.get('eps_quarterly', [])
                cash_flow_quarterly = quarterly_data.get('cash_flow_quarterly', [])

                quarters_stored = 0
                for i in range(len(revenue_quarterly)):
                    year = revenue_quarterly[i]['year']
                    quarter = revenue_quarterly[i]['quarter']
                    period = quarter  # quarter is already 'Q1', 'Q2', etc.

                    # Get corresponding data from other metrics
                    revenue = revenue_quarterly[i].get('revenue')
                    net_income = net_income_quarterly[i].get('net_income') if i < len(net_income_quarterly) else None
                    eps = eps_quarterly[i].get('eps') if i < len(eps_quarterly) else None

                    operating_cash_flow = None
                    capital_expenditures = None
                    free_cash_flow = None
                    if i < len(cash_flow_quarterly):
                        operating_cash_flow = cash_flow_quarterly[i].get('operating_cash_flow')
                        capital_expenditures = cash_flow_quarterly[i].get('capital_expenditures')
                        free_cash_flow = cash_flow_quarterly[i].get('free_cash_flow')

                    # Save to earnings_history
                    self.db.save_earnings_history(
                        symbol=symbol,
                        year=year,
                        eps=eps,
                        revenue=revenue,
                        period=period,
                        net_income=net_income,
                        operating_cash_flow=operating_cash_flow,
                        capital_expenditures=capital_expenditures,
                        free_cash_flow=free_cash_flow
                    )
                    quarters_stored += 1

                logger.info(f"[{symbol}] Cached {quarters_stored} quarters from 10-K/10-Q filings")
                return {'symbol': symbol, 'status': 'success', 'quarters': quarters_stored}

            except Exception as e:
                logger.error(f"[{symbol}] Error caching quarterly data: {e}")
                return None

        # Process stocks with moderate parallelism
        from concurrent.futures import ThreadPoolExecutor
        processed_count = 0
        success_count = 0
        current_count = 0
        failed_count = 0

        BATCH_SIZE = 10
        MAX_WORKERS = 6  # Moderate for 10-Q parsing

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            for i in range(0, total, BATCH_SIZE):
                batch = all_symbols[i:i + BATCH_SIZE]
                futures = {executor.submit(process_stock, symbol): symbol for symbol in batch}

                for future in futures:
                    result = future.result()
                    processed_count += 1

                    if result:
                        if result.get('status') == 'current':
                            current_count += 1
                        else:
                            success_count += 1
                    else:
                        failed_count += 1

                    if processed_count % 10 == 0:
                        progress_pct = 10 + int((processed_count / total) * 85)
                        self.db.update_job_progress(
                            job_id,
                            progress_pct=progress_pct,
                            progress_message=f'Processed {processed_count}/{total} stocks (updated: {success_count}, current: {current_count}, failed: {failed_count})',
                            processed_count=processed_count
                        )
                        self._send_heartbeat(job_id)

        # Complete
        result_message = f" : {success_count} updated, {current_count} already current, {failed_count} failed out of {total} stocks"
        self.db.complete_job(job_id, result=result_message)
        logger.info(result_message)

    def _run_price_update(self, job_id: int, params: Dict[str, Any]):
        """
        Fast price update job.
        Fetches basic market data (price, volume, change, etc.) for ALL stocks
        using TradingView scanner API (very fast, ~1-2 requests).
        """
        logger.info(f"Starting price update job {job_id}")
        self.db.update_job_progress(job_id, progress_pct=5, progress_message='Fetching market data from TradingView...')

        from tradingview_fetcher import TradingViewFetcher

        try:
            # fetch_all_stocks gets data for relevant regions (defaults to US/Europe/Asia)
            # We want to force it to just US if we want it super fast, or all if we want global coverage
            # Using same default as screening (all configured regions)
            tv_fetcher = TradingViewFetcher()

            # Using a large limit to get everything.
            # Region filter can be passed in params if needed, defaulting to 'us' for speed/relevance
            # based on user request "ALL US stocks"
            regions = params.get('regions', ['us'])
            if isinstance(regions, str):
                regions = regions.split(',')

            market_data = tv_fetcher.fetch_all_stocks(limit=20000, regions=regions)

            total_count = len(market_data)
            logger.info(f"Fetched {total_count} stocks from TradingView")

            self.db.update_job_progress(job_id, progress_pct=20, progress_message=f'Updating {total_count} stocks...', total_count=total_count)

            # Get list of all existing symbols in DB to validate against
            # This is crucial to avoid ForeignKeyViolations if TradingView returns a symbol we don't track
            # (e.g., preferred shares that slipped through filters, or new listings not yet in our DB)
            with self.db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT symbol FROM stocks")
                    existing_symbols = {row[0] for row in cursor.fetchall()}

            logger.info(f"Loaded {len(existing_symbols)} existing symbols from DB for validation")

            updated_count = 0

            # Batch updates are handled by the DB writer thread, so we can just loop and call update
            # We only want to update keys that change frequently
            for symbol, data in market_data.items():
                if not symbol:
                    continue

                # Normalize symbol to match DB (BIO.B -> BIO-B)
                # This mirrors logic in YFinancePriceClient._normalize_symbol
                symbol = symbol.replace('.', '-')

                # SKIP if not in our database
                if symbol not in existing_symbols:
                    continue

                # TradingViewFetcher returns normalized dict. We only need specific fields for price update.
                metrics = {
                    'price': data.get('price'),
                    'pe_ratio': data.get('pe_ratio'),
                    'market_cap': data.get('market_cap'),
                    'volume': data.get('volume'),
                    'dividend_yield': data.get('dividend_yield'),
                    'beta': data.get('beta'),
                    'total_revenue': data.get('total_revenue'),
                    'total_debt': data.get('total_debt'),
                }

                # Check if we have valid price (essential)
                if metrics.get('price') is None:
                    continue

                # Use TradingView's official daily change data (from previous market close)
                price = metrics['price']
                price_change = data.get('price_change')
                price_change_pct = data.get('price_change_pct')

                if price_change is not None and price_change_pct is not None:
                    # Calculate prev_close from current price and change
                    metrics['prev_close'] = price - price_change
                    metrics['price_change'] = price_change
                    metrics['price_change_pct'] = price_change_pct
                else:
                    # No change data available (market closed, new listing, etc.)
                    metrics['prev_close'] = None
                    metrics['price_change'] = None
                    metrics['price_change_pct'] = None

                self.db.save_stock_metrics(symbol, metrics)
                updated_count += 1

                if updated_count % 1000 == 0:
                    pct = 20 + int((updated_count / total_count) * 75)
                    self.db.update_job_progress(job_id, progress_pct=pct, processed_count=updated_count)
                    self._send_heartbeat(job_id)

            # Ensure all writes are committed
            self.db.flush()

            # Snapshot all portfolio values with updated prices
            snapshot_count = self._snapshot_portfolio_values()

            result = {
                'total_fetched': total_count,
                'updated_count': updated_count,
                'portfolio_snapshots': snapshot_count
            }
            self.db.complete_job(job_id, result)
            logger.info(f"Price update job completed. Updated {updated_count} stocks, {snapshot_count} portfolio snapshots.")

        except Exception as e:
            logger.error(f"Price update job failed: {e}")
            self.db.fail_job(job_id, str(e))

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
        from worker.core import get_memory_mb, check_memory_warning

        limit = params.get('limit')
        region = params.get('region', 'us')

        logger.info(f"Starting price history cache job {job_id} (region={region})")

        from yfinance_price_client import YFinancePriceClient
        from tradingview_fetcher import TradingViewFetcher
        from price_history_fetcher import PriceHistoryFetcher

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

                # Flush write queue every 100 symbols (non-blocking)
                self.db.flush_async()

        # Final flush to ensure all queued writes are committed
        self.db.flush()

        # Complete job
        result = {
            'total_stocks': total,  # Original total before skipping
            'processed': processed,
            'cached': cached,
            'skipped': skipped,
            'errors': errors
        }
        # Flush write queue before completing job
        self.db.flush()
        self.db.complete_job(job_id, result)
        logger.info(f"Price history cache complete: {result}")

    def _run_process_dividends(self, job_id: int, params: Dict[str, Any]):
        """Execute dividend processing for all portfolios"""
        from datetime import datetime

        logger.info(f"Running process_dividends job {job_id}")

        try:
            target_date_str = params.get('target_date')
            target_date = None
            if target_date_str:
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()

            self.db.update_job_progress(job_id, progress_pct=10, progress_message='Checking dividends for all portfolio holdings...')

            # This is a bit of a wrapper around the manager logic
            # to provide progress updates if possible, but manager handles the bulk.
            self.dividend_manager.process_all_portfolios(target_date=target_date)

            self.db.complete_job(job_id, result={'status': 'completed'})
            logger.info("Dividend processing complete")

        except Exception as e:
            logger.error(f"Dividend processing job failed: {e}")
            self.db.fail_job(job_id, str(e))
