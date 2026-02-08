# ABOUTME: Content caching job mixins for the background worker
# ABOUTME: Handles news, outlook, transcript, and forward metrics caching

import os
import time
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from news_fetcher import NewsFetcher

logger = logging.getLogger(__name__)


class ContentJobsMixin:
    """Mixin for content caching jobs: news, outlook, transcripts, forward metrics"""

    def _run_news_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache news articles for all stocks via Finnhub.

        Uses TradingView to get stock list (same as screening/prices) with region filtering.
        Symbols are sorted by score (STRONG_BUY first) when available.

        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            symbols: Optional list of specific symbols to process (for testing)
        """
        from worker.core import get_memory_mb, check_memory_warning

        limit = params.get('limit')
        region = params.get('region', 'us')
        specific_symbols = params.get('symbols')

        logger.info(f"Starting news cache job {job_id} (region={region})")

        from finnhub_news import FinnhubNewsClient
        from tradingview_fetcher import TradingViewFetcher

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
        # Flush write queue before completing job
        self.db.flush()
        self.db.complete_job(job_id, result)
        logger.info(f"News cache complete: {result}")


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
        from worker.core import get_memory_mb, check_memory_warning
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
        MAX_WORKERS = 5 # Reduced from 8 to reduce DB pressure

        def fetch_outlook_data(symbol: str) -> bool:
            """Fetch forward metrics and insider trades for a single symbol."""
            from datetime import timedelta

            try:
                ticker = yf.Ticker(symbol)

                # Try to fetch info, handle yfinance API failures gracefully
                try:
                    info = ticker.info
                except (TypeError, AttributeError) as e:
                    logger.debug(f"[{symbol}] Failed to fetch info from yfinance: {e}")
                    return False
                except Exception as e:
                    # Handle rate limiting and other yfinance errors
                    if "Rate limited" in str(e) or "Too Many Requests" in str(e):
                        logger.warning(f"[{symbol}] Rate limited by Yahoo Finance, will retry later")
                        return False
                    logger.debug(f"[{symbol}] Error fetching info: {e}")
                    return False

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

                # Extract next earnings date from earnings_dates DataFrame
                # This gives us both past and future dates - we want the next future one
                next_earnings_date = None
                try:
                    earnings_dates_df = ticker.earnings_dates
                    if earnings_dates_df is not None and not earnings_dates_df.empty:
                        today = pd.Timestamp.now(tz='America/New_York').normalize()
                        for date_idx in earnings_dates_df.index:
                            # Convert to timezone-aware timestamp for comparison
                            earnings_ts = pd.Timestamp(date_idx)
                            if earnings_ts >= today:
                                next_earnings_date = earnings_ts.date()
                                break
                except Exception:
                    pass  # Earnings dates not available for all stocks

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

                # Calculate fiscal period end dates for each estimate period
                try:
                    # info is already fetched at the beginning of this function
                    most_recent_quarter = info.get('mostRecentQuarter')
                    last_fiscal_year_end = info.get('lastFiscalYearEnd')
                    next_fiscal_year_end = info.get('nextFiscalYearEnd')

                    if most_recent_quarter and last_fiscal_year_end and next_fiscal_year_end and estimates_data:
                        # Convert timestamps to dates
                        mrq_date = datetime.fromtimestamp(most_recent_quarter).date()
                        last_fye = datetime.fromtimestamp(last_fiscal_year_end).date()
                        next_fye = datetime.fromtimestamp(next_fiscal_year_end).date()

                        # Calculate quarter end dates by adding approximately 91 days (~3 months)
                        # '0q' = next quarter after most recent (current reporting quarter)
                        # '+1q' = quarter after that
                        # '0y' = current fiscal year end
                        # '+1y' = next fiscal year end (current FY + 1 year)
                        current_q_end = mrq_date + timedelta(days=91)
                        next_q_end = current_q_end + timedelta(days=91)

                        # Determine current fiscal year
                        current_fye = next_fye if next_fye > mrq_date else last_fye

                        period_dates = {
                            '0q': current_q_end,
                            '+1q': next_q_end,
                            '0y': current_fye,
                            '+1y': next_fye + timedelta(days=365) if next_fye == current_fye else next_fye
                        }

                        # Helper to calculate fiscal quarter number
                        def get_fiscal_quarter(period_end, fiscal_year_end):
                            """Calculate fiscal quarter (1-4) based on how many months before FY end."""
                            # Calculate months difference
                            months_diff = (fiscal_year_end.year - period_end.year) * 12 + (fiscal_year_end.month - period_end.month)

                            if months_diff < 0:
                                # Period is after fiscal year end, it's in the next fiscal year
                                months_diff += 12

                            # Q4 ends at fiscal year end (0-2 months before)
                            # Q3 ends ~3 months before (3-5 months before)
                            # Q2 ends ~6 months before (6-8 months before)
                            # Q1 ends ~9 months before (9-11 months before)
                            if 0 <= months_diff <= 2:
                                return 4
                            elif 3 <= months_diff <= 5:
                                return 3
                            elif 6 <= months_diff <= 8:
                                return 2
                            else:
                                return 1

                        # Add period_end_date and fiscal info to each estimate
                        for period, end_date in period_dates.items():
                            if period in estimates_data:
                                estimates_data[period]['period_end_date'] = end_date

                                # Add fiscal quarter/year info for quarterly periods
                                if period in ['0q', '+1q']:
                                    fye_for_period = current_fye if period == '0q' else (next_fye if next_q_end <= next_fye else next_fye + timedelta(days=365))
                                    fiscal_quarter = get_fiscal_quarter(end_date, fye_for_period)
                                    fiscal_year = fye_for_period.year % 100  # Last 2 digits
                                    estimates_data[period]['fiscal_quarter'] = fiscal_quarter
                                    estimates_data[period]['fiscal_year'] = fiscal_year
                except Exception as e:
                    logger.debug(f"[{symbol}] Error calculating period dates: {e}")

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
                import traceback
                logger.error(f"[{symbol}] Outlook fetch error: {e}")
                logger.error(f"[{symbol}] Traceback:\n{traceback.format_exc()}")
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
        # Flush write queue before completing job
        self.db.flush()
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
        from worker.core import get_memory_mb, check_memory_warning

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

        # Pre-compute skip list BEFORE entering async context to avoid blocking DB calls
        # This keeps all synchronous DB work outside the async function
        skip_set = set()

        if not force_refresh:
            logger.info("Pre-computing skip list based on earnings dates...")
            try:
                from datetime import datetime, timedelta, date
                today = datetime.now().date()
                refresh_metadata = self.db.get_earnings_refresh_metadata()

                for symbol in all_symbols:
                    meta = refresh_metadata.get(symbol, {})
                    next_date = meta.get('next_earnings_date')
                    last_date = meta.get('last_transcript_date')

                    # Default target: if no data, assume we want a recent one
                    target_date = None

                    if next_date:
                        if next_date <= today:
                            # Event passed or is today -> we want this transcript
                            target_date = next_date
                        else:
                            # next_date is future -> we likely want the PREVIOUS quarter
                            # Assume previous quarter was ~91 days ago
                            target_date = next_date - timedelta(days=91)

                    # Check if we have it
                    should_skip = False
                    if last_date and target_date:
                        # Allow 10 days buffer (e.g. if transcript is dated slightly before official earnings date)
                        if last_date >= (target_date - timedelta(days=10)):
                            should_skip = True
                            
                            # RETRY LOGIC: If the last attempt was a failure (placeholder) AND
                            # we are still within the 7-day retry window, force a retry.
                            is_placeholder = meta.get('latest_is_placeholder', False)
                            days_since_target = (today - target_date).days
                            
                            if is_placeholder and days_since_target <= 7:
                                should_skip = False

                    elif last_date and not target_date:
                        # If we have a transcript but no next date info, rely on age
                        # Skip if less than 75 days old
                        if (today - last_date).days < 75:
                            should_skip = True

                    # Expiration policy: Give up if target date was more than 7 days ago
                    # This prevents infinite retries for stocks that don't publish transcripts
                    if not should_skip and target_date:
                        if (today - target_date).days > 7:
                            should_skip = True

                    if should_skip:
                        skip_set.add(symbol)

                    # Logging for debug (only for first few or specific)
                    if symbol == 'MSFT' or symbol == 'NVDA':
                        logger.info(f"[{symbol}] Smart Fetch Check: Next={next_date}, Last={last_date}, Target={target_date} -> {'SKIP' if should_skip else 'FETCH'}")

            except Exception as e:
                logger.error(f"Error pre-computing skip list: {e}")

            logger.info(f"Will skip {len(skip_set)} stocks based on earnings dates")

        # Filter all_symbols to only include those that need processing
        # This ensures the progress bar reflects the actual work to be done
        initial_count = len(all_symbols)
        symbols_to_process = [s for s in all_symbols if s not in skip_set]

        total = len(symbols_to_process)
        skipped_initial = initial_count - total

        logger.info(f"Caching transcripts for {total} stocks (skipping {skipped_initial} based on cache/earnings dates)")

        self.db.update_job_progress(job_id, progress_pct=10,
                                    progress_message=f'Caching transcripts for {total} stocks (skipped {skipped_initial})...',
                                    processed_count=0,
                                    total_count=total)

        # Initialize scraper (Playwright session) - runs async
        processed = 0
        cached = 0
        skipped = skipped_initial # Track total skipped including pre-skipped
        errors = 0

        async def run_transcript_caching():
            nonlocal processed, cached, skipped, errors

            logger.info("Starting async transcript scraper...")
            async with TranscriptScraper() as scraper:
                logger.info("Browser started successfully")

                for symbol in symbols_to_process:
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
                            # Determine the best estimated earnings date for the marker
                            marker_date = datetime.now().date()
                            try:
                                # Strategy 1: Use next_earnings_date - 91 days (if likely just missed previous)
                                metrics = self.db.get_stock_metrics(symbol)
                                next_date = metrics.get('next_earnings_date') if metrics else None
                                
                                if next_date:
                                    if next_date > marker_date:
                                        marker_date = next_date - timedelta(days=91)
                                    else:
                                        marker_date = next_date
                                else:
                                    # Strategy 2: Use most recent fiscal_end from earnings history
                                    history = self.db.get_earnings_history(symbol, period_type='quarterly')
                                    if history and len(history) > 0:
                                        # History is ordered by year DESC, period (ASC by default in DB)
                                        # We want the most recent one so we re-sort to be safe
                                        # Sort by year DESC, period DESC (Q4 > Q1)
                                        history.sort(key=lambda x: (x['year'], x['period']), reverse=True)
                                        
                                        latest = history[0]
                                        if latest.get('fiscal_end'):
                                            # fiscal_end is usually a string YYYY-MM-DD
                                            try:
                                                f_end = datetime.strptime(latest['fiscal_end'], '%Y-%m-%d').date()
                                                marker_date = f_end
                                            except:
                                                pass
                            except Exception as e:
                                logger.warning(f"[{symbol}] Error estimating marker date: {e}")

                            # Save a marker record with "NO_TRANSCRIPT" so we skip this stock in future runs
                            logger.info(f"[{symbol}] No transcript available - saving marker to skip in future (date={marker_date})")
                            self.db.save_earnings_transcript(symbol, {
                                'quarter': 'N/A',
                                'fiscal_year': 0,
                                'transcript_text': 'NO_TRANSCRIPT_AVAILABLE',
                                'has_qa': False,
                                'participants': [],
                                'source_url': '',
                                'earnings_date': marker_date
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

                    if processed % 50 == 0 and processed > 0:
                        logger.info(f"Transcript cache progress: {processed}/{total} (cached: {cached}, skipped: {skipped}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                        check_memory_warning(f"[transcript {processed}/{total}]")
                        # Restart browser periodically to prevent memory buildup
                        await scraper.restart_browser()

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
        # Flush write queue before completing job
        self.db.flush()
        self.db.complete_job(job_id, result)
        logger.info(f"Transcript cache complete: {result}")

    def _run_forward_metrics_cache(self, job_id: int, params: Dict[str, Any]):
        """
        Cache forward metrics (forward PE, estimates, trends, recommendations) for all stocks.

        Fetches from yfinance:
        - ticker.info: forward_pe, forward_eps, forward_peg, price targets, recommendations
        - ticker.earnings_estimate / revenue_estimate: quarterly and annual estimates
        - ticker.eps_trend: how estimates changed over 7/30/60/90 days
        - ticker.eps_revisions: upward/downward revision counts
        - ticker.growth_estimates: stock vs index growth comparison
        - ticker.recommendations: monthly analyst buy/hold/sell distribution

        Params:
            limit: Optional max number of stocks to process
            region: Region filter (us, north-america, europe, asia, all)
            symbols: Optional list of specific symbols to process (for testing)
        """
        from worker.core import get_memory_mb, check_memory_warning
        import yfinance as yf
        import pandas as pd

        limit = params.get('limit')
        region = params.get('region', 'us')
        specific_symbols = params.get('symbols')

        logger.info(f"Starting forward metrics cache job {job_id} (region={region})")

        from tradingview_fetcher import TradingViewFetcher

        # If specific symbols provided, use those directly (for testing)
        if specific_symbols:
            all_symbols = specific_symbols
            logger.info(f"Using specific symbols: {all_symbols}")
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Processing {len(all_symbols)} specific symbols...')
        else:
            # Map CLI region to TradingView regions
            region_mapping = {
                'us': ['us'],
                'north-america': ['north_america'],
                'south-america': ['south_america'],
                'europe': ['europe'],
                'asia': ['asia'],
                'all': None
            }
            tv_regions = region_mapping.get(region, ['us'])

            # Get stock list from TradingView
            self.db.update_job_progress(job_id, progress_pct=5, progress_message=f'Fetching stock list from TradingView ({region})...')
            tv_fetcher = TradingViewFetcher()
            market_data_cache = tv_fetcher.fetch_all_stocks(limit=20000, regions=tv_regions)

            # Ensure all stocks exist in DB before caching
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

        total = len(all_symbols)
        self.db.update_job_progress(job_id, progress_pct=10, progress_message=f'Fetching forward metrics for {total} stocks...',
                                    total_count=total)

        logger.info(f"Ready to fetch forward metrics for {total} stocks")

        processed = 0
        cached = 0
        errors = 0

        for symbol in all_symbols:
            try:
                ticker = yf.Ticker(symbol)

                # Fetch info (forward PE, price targets, recommendations)
                try:
                    info = ticker.info
                    if info:
                        forward_data = {
                            'forward_pe': info.get('forwardPE'),
                            'forward_eps': info.get('forwardEps'),
                            'forward_peg_ratio': info.get('pegRatio') or info.get('trailingPegRatio'),
                            'price_target_high': info.get('targetHighPrice'),
                            'price_target_low': info.get('targetLowPrice'),
                            'price_target_mean': info.get('targetMeanPrice'),
                            'price_target_median': info.get('targetMedianPrice'),
                            'analyst_rating': info.get('averageAnalystRating'),
                            'analyst_rating_score': info.get('recommendationMean'),
                            'analyst_count': info.get('numberOfAnalystOpinions'),
                            'recommendation_key': info.get('recommendationKey'),
                            'earnings_growth': info.get('earningsGrowth'),
                            'earnings_quarterly_growth': info.get('earningsQuarterlyGrowth'),
                            'revenue_growth': info.get('revenueGrowth'),
                        }
                        self.db.update_forward_metrics(symbol, forward_data)
                except Exception as e:
                    logger.debug(f"[{symbol}] Could not fetch info: {e}")

                # Fetch earnings/revenue estimates
                try:
                    earnings_est = ticker.earnings_estimate
                    revenue_est = ticker.revenue_estimate

                    if earnings_est is not None and not earnings_est.empty:
                        estimates_data = {}
                        for period in earnings_est.index:
                            row = earnings_est.loc[period]
                            estimates_data[period] = {
                                'eps_avg': row.get('avg') if pd.notna(row.get('avg')) else None,
                                'eps_low': row.get('low') if pd.notna(row.get('low')) else None,
                                'eps_high': row.get('high') if pd.notna(row.get('high')) else None,
                                'eps_growth': row.get('growth') if pd.notna(row.get('growth')) else None,
                                'eps_year_ago': row.get('yearAgoEps') if pd.notna(row.get('yearAgoEps')) else None,
                                'eps_num_analysts': int(row.get('numberOfAnalysts')) if pd.notna(row.get('numberOfAnalysts')) else None,
                            }
                            # Add revenue estimates for same period if available
                            if revenue_est is not None and not revenue_est.empty and period in revenue_est.index:
                                rev_row = revenue_est.loc[period]
                                estimates_data[period]['revenue_avg'] = rev_row.get('avg') if pd.notna(rev_row.get('avg')) else None
                                estimates_data[period]['revenue_low'] = rev_row.get('low') if pd.notna(rev_row.get('low')) else None
                                estimates_data[period]['revenue_high'] = rev_row.get('high') if pd.notna(rev_row.get('high')) else None
                                estimates_data[period]['revenue_growth'] = rev_row.get('growth') if pd.notna(rev_row.get('growth')) else None
                                estimates_data[period]['revenue_year_ago'] = rev_row.get('yearAgoRevenue') if pd.notna(rev_row.get('yearAgoRevenue')) else None
                                estimates_data[period]['revenue_num_analysts'] = int(rev_row.get('numberOfAnalysts')) if pd.notna(rev_row.get('numberOfAnalysts')) else None

                        self.db.save_analyst_estimates(symbol, estimates_data)
                except Exception as e:
                    logger.debug(f"[{symbol}] Could not fetch estimates: {e}")

                # Fetch EPS trends
                try:
                    eps_trend = ticker.eps_trend
                    if eps_trend is not None and not eps_trend.empty:
                        trends_data = {}
                        for period in eps_trend.index:
                            row = eps_trend.loc[period]
                            trends_data[period] = {
                                'current': row.get('current') if pd.notna(row.get('current')) else None,
                                '7daysAgo': row.get('7daysAgo') if pd.notna(row.get('7daysAgo')) else None,
                                '30daysAgo': row.get('30daysAgo') if pd.notna(row.get('30daysAgo')) else None,
                                '60daysAgo': row.get('60daysAgo') if pd.notna(row.get('60daysAgo')) else None,
                                '90daysAgo': row.get('90daysAgo') if pd.notna(row.get('90daysAgo')) else None,
                            }
                        self.db.save_eps_trends(symbol, trends_data)
                except Exception as e:
                    logger.debug(f"[{symbol}] Could not fetch eps_trend: {e}")

                # Fetch EPS revisions
                try:
                    eps_revisions = ticker.eps_revisions
                    if eps_revisions is not None and not eps_revisions.empty:
                        revisions_data = {}
                        for period in eps_revisions.index:
                            row = eps_revisions.loc[period]
                            revisions_data[period] = {
                                'upLast7days': int(row.get('upLast7days')) if pd.notna(row.get('upLast7days')) else None,
                                'upLast30days': int(row.get('upLast30days')) if pd.notna(row.get('upLast30days')) else None,
                                'downLast7Days': int(row.get('downLast7Days')) if pd.notna(row.get('downLast7Days')) else None,
                                'downLast30days': int(row.get('downLast30days')) if pd.notna(row.get('downLast30days')) else None,
                            }
                        self.db.save_eps_revisions(symbol, revisions_data)
                except Exception as e:
                    logger.debug(f"[{symbol}] Could not fetch eps_revisions: {e}")

                # Fetch growth estimates
                try:
                    growth_est = ticker.growth_estimates
                    if growth_est is not None and not growth_est.empty:
                        growth_data = {}
                        for period in growth_est.index:
                            row = growth_est.loc[period]
                            growth_data[period] = {
                                'stockTrend': row.get('stockTrend') if pd.notna(row.get('stockTrend')) else None,
                                'indexTrend': row.get('indexTrend') if pd.notna(row.get('indexTrend')) else None,
                            }
                        self.db.save_growth_estimates(symbol, growth_data)
                except Exception as e:
                    logger.debug(f"[{symbol}] Could not fetch growth_estimates: {e}")

                # Fetch recommendations
                try:
                    recommendations = ticker.recommendations
                    if recommendations is not None and not recommendations.empty:
                        recs_data = []
                        for _, row in recommendations.iterrows():
                            recs_data.append({
                                'period': row.get('period'),
                                'strongBuy': int(row.get('strongBuy')) if pd.notna(row.get('strongBuy')) else None,
                                'buy': int(row.get('buy')) if pd.notna(row.get('buy')) else None,
                                'hold': int(row.get('hold')) if pd.notna(row.get('hold')) else None,
                                'sell': int(row.get('sell')) if pd.notna(row.get('sell')) else None,
                                'strongSell': int(row.get('strongSell')) if pd.notna(row.get('strongSell')) else None,
                            })
                        self.db.save_analyst_recommendations(symbol, recs_data)
                except Exception as e:
                    logger.debug(f"[{symbol}] Could not fetch recommendations: {e}")

                cached += 1

            except Exception as e:
                logger.warning(f"[{symbol}] Forward metrics cache error: {e}")
                errors += 1

            processed += 1

            # Update progress every 50 stocks
            if processed % 50 == 0 or processed == total:
                pct = 10 + int((processed / total) * 85)
                self.db.update_job_progress(
                    job_id,
                    progress_pct=pct,
                    progress_message=f'Fetched {processed}/{total} stocks ({cached} cached, {errors} errors)',
                    processed_count=processed,
                    total_count=total
                )
                self._send_heartbeat(job_id)

            if processed % 100 == 0:
                logger.info(f"Forward metrics cache progress: {processed}/{total} (cached: {cached}, errors: {errors}) | MEMORY: {get_memory_mb():.0f}MB")
                check_memory_warning(f"[forward_metrics {processed}/{total}]")

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
        logger.info(f"Forward metrics cache complete: {result}")
