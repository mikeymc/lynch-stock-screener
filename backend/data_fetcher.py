# ABOUTME: Fetches stock data using hybrid EDGAR + yfinance approach
# ABOUTME: Uses EDGAR for fundamentals, yfinance for current market data

import yfinance as yf
import logging
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from database import Database
from edgar_fetcher import EdgarFetcher
import pandas as pd
import logging
import socket
from yfinance_rate_limiter import with_timeout_and_retry

logger = logging.getLogger(__name__)

# Note: Socket timeout is now handled by yfinance_rate_limiter decorator
# which provides better timeout control with retry logic


def retry_on_rate_limit(max_retries=3, initial_delay=1.0):
    """Decorator to retry API calls with exponential backoff on rate limit errors"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).lower()
                    # Check for rate limit indicators
                    if '429' in error_msg or 'rate limit' in error_msg or 'too many requests' in error_msg:
                        if attempt < max_retries - 1:
                            logger.warning(f"Rate limit hit in {func.__name__}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                            time.sleep(delay)
                            delay *= 2  # Exponential backoff
                            continue
                    # Re-raise if not a rate limit error or max retries exceeded
                    raise
            return None
        return wrapper
    return decorator



class DataFetcher:
    def __init__(self, db: Database):
        self.db = db
        # Pass database instance to EdgarFetcher (it will get/return connections as needed)
        self.edgar_fetcher = EdgarFetcher(
            user_agent="Lynch Stock Screener mikey@example.com",
            db=db
        )

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance info")
    def _get_yf_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch yfinance info with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.info

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance financials")
    def _get_yf_financials(self, symbol: str):
        """Fetch yfinance financials with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.financials

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance balance_sheet")
    def _get_yf_balance_sheet(self, symbol: str):
        """Fetch yfinance balance sheet with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.balance_sheet

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance quarterly_financials")
    def _get_yf_quarterly_financials(self, symbol: str):
        """Fetch yfinance quarterly financials with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.quarterly_financials

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance quarterly_balance_sheet")
    def _get_yf_quarterly_balance_sheet(self, symbol: str):
        """Fetch yfinance quarterly balance sheet with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.quarterly_balance_sheet

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance history")
    def _get_yf_history(self, symbol: str):
        """Fetch yfinance price history with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.history(period="max")

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance cashflow")
    def _get_yf_cashflow(self, symbol: str):
        """Fetch yfinance cash flow with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.cashflow

    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance insider_transactions")
    def _get_yf_insider_transactions(self, symbol: str):
        """Fetch yfinance insider transactions with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.insider_transactions

    @retry_on_rate_limit(max_retries=3, initial_delay=1.0)
    def fetch_stock_data(self, symbol: str, force_refresh: bool = False, market_data_cache: Optional[Dict[str, Dict]] = None, finviz_cache: Optional[Dict[str, float]] = None) -> Optional[Dict[str, Any]]:
        if not force_refresh and self.db.is_cache_valid(symbol):
            return self.db.get_stock_metrics(symbol)

        try:
            # Try fetching fundamentals from EDGAR first
            logger.info(f"[{symbol}] Attempting EDGAR fetch")
            edgar_data = self.edgar_fetcher.fetch_stock_fundamentals(symbol)

            # Get market data from TradingView cache or fetch from yfinance
            using_tradingview_cache = False
            if market_data_cache and symbol in market_data_cache:
                # Use pre-fetched TradingView data
                cached_data = market_data_cache[symbol]
                info = {
                    'symbol': symbol,
                    'currentPrice': cached_data.get('price'),
                    'regularMarketPrice': cached_data.get('price'),
                    'marketCap': cached_data.get('market_cap'),
                    'trailingPE': cached_data.get('pe_ratio'),
                    'dividendYield': cached_data.get('dividend_yield'),
                    'beta': cached_data.get('beta'),
                    'sector': cached_data.get('sector'),
                    'industry': cached_data.get('industry'),
                    # Add placeholders for fields TradingView doesn't have
                    'longName': cached_data.get('company_name') or symbol,
                    'exchange': cached_data.get('exchange', 'UNKNOWN'),
                    'country': cached_data.get('country'),  # May be None, will fetch from yfinance if needed
                    'totalRevenue': None,
                    'totalDebt': None,
                    'heldPercentInstitutions': None,
                }
                using_tradingview_cache = True
                logger.info(f"[{symbol}] Using TradingView cached market data")
            else:
                # Fallback to individual yfinance call
                logger.warning(f"⚠️  [{symbol}] NOT IN TRADINGVIEW CACHE - Falling back to slow yfinance API call")
                info = self._get_yf_info(symbol)

            if not info or 'symbol' not in info:
                logger.error(f"❌ [{symbol}] Failed to fetch market data (not in TradingView cache, yfinance also failed)")
                return None

            company_name = info.get('longName', '')
            exchange = info.get('exchange', '')
            sector = info.get('sector', '')
            
            # Get country from TradingView cache or yfinance
            country = info.get('country', '')
            
            # If country is missing and we're using TradingView cache, try yfinance for country only
            if not country and using_tradingview_cache:
                try:
                    logger.info(f"[{symbol}] Country missing from TradingView, fetching from yfinance")
                    yf_info = self._get_yf_info(symbol)
                    if yf_info:
                        country = yf_info.get('country', '')
                except Exception as e:
                    logger.warning(f"[{symbol}] Failed to fetch country from yfinance: {e}")
            
            # Normalize country to 2-letter code
            if country:
                from country_codes import normalize_country_code
                country = normalize_country_code(country)

            # Calculate IPO year from firstTradeDateMilliseconds or firstTradeDateEpochUtc
            ipo_year = None
            first_trade_millis = info.get('firstTradeDateMilliseconds')
            first_trade_epoch = info.get('firstTradeDateEpochUtc')
            if first_trade_millis:
                from datetime import datetime as dt
                ipo_year = dt.fromtimestamp(first_trade_millis / 1000).year
            elif first_trade_epoch:
                from datetime import datetime as dt
                ipo_year = dt.fromtimestamp(first_trade_epoch).year
            
            # Fallback: Use earliest revenue year from EDGAR if IPO year is missing
            if not ipo_year and edgar_data and edgar_data.get('revenue_history'):
                years = [entry['year'] for entry in edgar_data['revenue_history']]
                if years:
                    ipo_year = min(years)
                    logger.info(f"[{symbol}] Estimated IPO year from EDGAR revenue history: {ipo_year}")

            self.db.save_stock_basic(symbol, company_name, exchange, sector, country, ipo_year)

            # Use EDGAR debt-to-equity if available, otherwise fall back to yfinance
            debt_to_equity = None
            if edgar_data and edgar_data.get('debt_to_equity'):
                debt_to_equity = edgar_data['debt_to_equity']
            else:
                debt_to_equity_pct = info.get('debtToEquity', 0)
                debt_to_equity = debt_to_equity_pct / 100 if debt_to_equity_pct else None

            # Use yfinance for current market data (price, P/E, market cap)
            # yfinance returns dividendYield already as percentage (e.g., 2.79 for 2.79%)
            dividend_yield = info.get('dividendYield')

            # Get institutional ownership from Finviz cache if available, otherwise yfinance
            institutional_ownership = None
            if finviz_cache and symbol in finviz_cache:
                institutional_ownership = finviz_cache[symbol]
                logger.info(f"[{symbol}] Using Finviz cached institutional ownership: {institutional_ownership:.1%}")
            elif not using_tradingview_cache and info:
                # Only fallback to yfinance if NOT using TradingView cache
                # (TradingView cache explicitly sets heldPercentInstitutions to None)
                institutional_ownership = info.get('heldPercentInstitutions')
                if institutional_ownership is not None:
                    logger.warning(f"⚠️  [{symbol}] NOT IN FINVIZ CACHE - Using yfinance institutional ownership")

            # Fetch WACC-related data
            beta = info.get('beta')
            total_debt = info.get('totalDebt')

            # If using TradingView cache and total_debt is missing, fetch from yfinance
            # This is needed for Buffett's debt-to-earnings calculation
            if total_debt is None and using_tradingview_cache:
                try:
                    yf_info = self._get_yf_info(symbol)
                    if yf_info:
                        total_debt = yf_info.get('totalDebt')
                        logger.info(f"[{symbol}] Fetched total_debt from yfinance: {total_debt}")
                except Exception as e:
                    logger.warning(f"[{symbol}] Failed to fetch total_debt from yfinance: {e}")

            # Fallback for Debt-to-Equity if missing from EDGAR and yfinance info
            if debt_to_equity is None:
                logger.info(f"[{symbol}] D/E missing from info, attempting calculation from balance sheet")
                try:
                    balance_sheet = self._get_yf_balance_sheet(symbol)
                    if balance_sheet is not None and not balance_sheet.empty:
                        # Get most recent column
                        recent_col = balance_sheet.columns[0]
                        calc_de, calc_total_debt = self._calculate_debt_to_equity(balance_sheet, recent_col)
                        if calc_de is not None:
                            debt_to_equity = calc_de
                            logger.info(f"[{symbol}] Calculated D/E from balance sheet: {debt_to_equity:.2f}")
                        # Also capture total_debt if we found it and don't already have it
                        if calc_total_debt is not None and total_debt is None:
                            total_debt = calc_total_debt
                            logger.info(f"[{symbol}] Captured total_debt from balance sheet: {total_debt:,.0f}")
                except Exception as e:
                    logger.warning(f"[{symbol}] Failed to calculate D/E from balance sheet: {e}")
            
            # Get interest expense and tax rate from financials (SKIP if using TradingView cache for speed)
            interest_expense = None
            effective_tax_rate = None
            
            if not using_tradingview_cache:
                # Only fetch these slow yfinance calls if NOT using TradingView cache
                try:
                    ticker = yf.Ticker(symbol)
                    financials = ticker.financials
                    if financials is not None and not financials.empty:
                        if 'Interest Expense' in financials.index:
                            interest_expense = abs(financials.loc['Interest Expense'].iloc[0])
                except Exception as e:
                    logger.debug(f"Could not fetch interest expense for {symbol}: {e}")
                
                # Calculate effective tax rate from income statement
                try:
                    if financials is not None and not financials.empty:
                        if 'Tax Provision' in financials.index and 'Pretax Income' in financials.index:
                            tax = financials.loc['Tax Provision'].iloc[0]
                            pretax = financials.loc['Pretax Income'].iloc[0]
                            if pretax and pretax > 0:
                                effective_tax_rate = tax / pretax
                except Exception as e:
                    logger.debug(f"Could not calculate tax rate for {symbol}: {e}")

            metrics = {
                'price': info.get('currentPrice'),
                'pe_ratio': info.get('trailingPE'),
                'market_cap': info.get('marketCap'),
                'debt_to_equity': debt_to_equity,
                'institutional_ownership': institutional_ownership,
                'revenue': info.get('totalRevenue'),
                'dividend_yield': dividend_yield,
                'beta': beta,
                'total_debt': total_debt,
                'interest_expense': interest_expense,
                'effective_tax_rate': effective_tax_rate,
                # New Future Indicators
                'forward_pe': info.get('forwardPE'),
                'forward_peg_ratio': info.get('pegRatio') if info.get('pegRatio') else info.get('trailingPegRatio'), # Prefer 5yr exepcted, fallback to trailing
                'forward_eps': info.get('forwardEps'),
                # insider_net_buying_6m removed - calculated by worker from Form 4 data only
            }

            # Legacy insider transaction fetching removed (moved to Form 4 worker)
            # self.db.save_insider_trades(symbol, trades_to_save)

            self.db.save_stock_metrics(symbol, metrics)
            # Use EDGAR net income if available (≥5 years), otherwise fall back to yfinance
            # ALWAYS process EDGAR data if available (even if using TradingView cache) to get growth rates
            if edgar_data and edgar_data.get('net_income_annual') and edgar_data.get('revenue_history'):
                net_income_count = len(edgar_data.get('net_income_annual', []))
                rev_count = len(edgar_data.get('revenue_history', []))

                # Check that we have matching years for net income and revenue
                net_income_years = {entry['year'] for entry in edgar_data.get('net_income_annual', [])}
                rev_years = {entry['year'] for entry in edgar_data.get('revenue_history', [])}
                matched_years = len(net_income_years & rev_years)

                logger.info(f"[{symbol}] EDGAR returned {net_income_count} net income years, {rev_count} revenue years, {matched_years} matched")

                # Use EDGAR only if we have >= 5 matched years, otherwise fall back to yfinance
                if matched_years >= 5:
                    logger.info(f"[{symbol}] Using EDGAR Net Income ({matched_years} years)")
                    
                    # Fetch price history for yield calculation (SKIP if using TradingView cache)
                    price_history = None
                    if not using_tradingview_cache:
                        price_history = self._get_yf_history(symbol)
                        
                    self._store_edgar_earnings(symbol, edgar_data, price_history)
                    
                    # Fetch quarterly data from EDGAR (SKIP if using TradingView cache)
                    if edgar_data.get('net_income_quarterly'):
                        logger.info(f"[{symbol}] Fetching quarterly Net Income from EDGAR")
                        # Only fetch price history if we haven't already and we're not using cache
                        # But quarterly storage also needs price history for yield... 
                        # Since we skip quarterly data for cache anyway, this is fine.
                        self._store_edgar_quarterly_earnings(symbol, edgar_data, price_history, force_refresh=force_refresh)
                    else:
                        if not using_tradingview_cache:
                            logger.warning(f"[{symbol}] No quarterly Net Income available, falling back to yfinance for quarterly data")
                            self._fetch_quarterly_earnings(symbol)
                else:
                    logger.info(f"[{symbol}] EDGAR has insufficient matched years ({matched_years} < 5). Falling back to yfinance")
                    if not using_tradingview_cache:
                        self._fetch_and_store_earnings(symbol)
                    else:
                        logger.info(f"[{symbol}] Skipping yfinance fallback (using TradingView cache)")
            else:
                if edgar_data:
                    net_income_count = len(edgar_data.get('net_income_annual', []))
                    rev_count = len(edgar_data.get('revenue_history', []))
                    logger.info(f"[{symbol}] Partial EDGAR data: {net_income_count} net income years, {rev_count} revenue years. Falling back to yfinance")
                else:
                    logger.info(f"[{symbol}] EDGAR fetch failed. Using yfinance")
                
                if not using_tradingview_cache:
                    self._fetch_and_store_earnings(symbol)
                else:
                    logger.info(f"[{symbol}] Skipping yfinance fallback (using TradingView cache)")

            # Flush queued writes to ensure data is committed
            self.db.flush()

            # Return the metrics directly instead of querying DB (supports async writes)
            # Add company info to metrics for completeness
            metrics.update({
                'company_name': company_name,
                'exchange': exchange,
                'sector': sector,
                'country': country,
                'ipo_year': ipo_year,
                'symbol': symbol
            })
            return metrics

        except Exception as e:
            print(f"Error fetching stock data for {symbol}: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # todo: do we need calcualted_eps_history? can we ditch eps altogether?
    # todo: rename to _store_edgar_annual_earnings
    def _store_edgar_earnings(self, symbol: str, edgar_data: Dict[str, Any], price_history: Optional[pd.DataFrame] = None):
        """Store earnings history from EDGAR data using Net Income"""
        # Use net_income_annual (raw Net Income from EDGAR)
        net_income_annual = edgar_data.get('net_income_annual', [])
        revenue_history = edgar_data.get('revenue_history', [])
        debt_to_equity_history = edgar_data.get('debt_to_equity_history', [])
        shareholder_equity_history = edgar_data.get('shareholder_equity_history', [])
        calculated_eps_history = edgar_data.get('calculated_eps_history', [])
        cash_flow_history = edgar_data.get('cash_flow_history', [])
        
        # Parse dividend history
        dividend_history = edgar_data.get('dividend_history', [])
        # Filter for annual dividends or aggregate quarterly if needed
        # For now, let's assume we can match by year. 
        # Note: EDGAR dividends might be quarterly. We should sum them up for annual.
        
        # Group dividends by year and period
        divs_grouped = {}
        for div in dividend_history:
            year = div['year']
            if year not in divs_grouped:
                divs_grouped[year] = {'annual': [], 'quarterly': []}
            
            if div.get('period') == 'annual':
                divs_grouped[year]['annual'].append(div['amount'])
            else:
                divs_grouped[year]['quarterly'].append(div['amount'])
        
        dividends_by_year = {}
        for year, groups in divs_grouped.items():
            if groups['annual']:
                # Use the max annual value (in case of duplicates/restatements)
                dividends_by_year[year] = max(groups['annual'])
            elif groups['quarterly']:
                # Sum quarterly values
                dividends_by_year[year] = sum(groups['quarterly'])

        # Create mapping of year to net income for easy lookup
        net_income_by_year = {entry['year']: {'net_income': entry['net_income'], 'fiscal_end': entry.get('fiscal_end')} for entry in net_income_annual}

        # Create mapping of year to debt_to_equity for easy lookup
        debt_to_equity_by_year = {entry['year']: entry['debt_to_equity'] for entry in debt_to_equity_history}
        
        # Create mapping of year to shareholder_equity for easy lookup
        shareholder_equity_by_year = {entry['year']: entry['shareholder_equity'] for entry in shareholder_equity_history}

        # Create mapping of year to EPS - prioritize calculated EPS, fallback to direct EPS
        # calculated_eps_history = Net Income / Shares Outstanding (split-adjusted)
        # eps_history = Direct EPS from SEC filings (may not be split-adjusted for older years)
        calculated_eps_by_year = {entry['year']: entry['eps'] for entry in calculated_eps_history}
        direct_eps_by_year = {entry['year']: entry['eps'] for entry in edgar_data.get('eps_history', [])}
        
        # Detect stock splits by looking for sudden large drops in direct EPS between adjacent years
        # This indicates a stock split occurred (e.g., 20:1 split would show EPS dropping by ~95%)
        split_year = None
        split_adjustment_factor = 1.0
        best_split_ratio = 0
        
        if len(direct_eps_by_year) >= 2:
            sorted_years = sorted(direct_eps_by_year.keys())
            common_splits = [2, 3, 4, 5, 10, 20, 50, 100]
            
            for i in range(len(sorted_years) - 1):
                year1, year2 = sorted_years[i], sorted_years[i + 1]
                eps1, eps2 = direct_eps_by_year[year1], direct_eps_by_year[year2]
                
                if eps1 and eps2 and eps1 > 0 and eps2 > 0:
                    # Check for sudden drop (split would cause EPS to drop significantly)
                    ratio = eps1 / eps2
                    # Use 30% tolerance to account for earnings changes in the same year as split
                    for split in common_splits:
                        if 0.7 * split <= ratio <= 1.3 * split:
                            # Only use this split if it's larger than previous matches
                            # This ensures we catch the biggest split (e.g., 20:1 not 2:1)
                            if split > best_split_ratio:
                                split_year = year2
                                split_adjustment_factor = split
                                best_split_ratio = split
                            break
        
        if split_year:
            logger.info(f"[{symbol}] Detected {int(split_adjustment_factor)}:1 stock split in {split_year} - will adjust pre-split EPS")
        
        # Merge: use calculated EPS if available, otherwise fall back to split-adjusted direct EPS
        eps_by_year = {}
        all_years = set(calculated_eps_by_year.keys()) | set(direct_eps_by_year.keys())
        for year in all_years:
            if year in calculated_eps_by_year:
                eps_by_year[year] = calculated_eps_by_year[year]
            elif year in direct_eps_by_year:
                # Apply split adjustment to direct EPS for years before the split
                raw_eps = direct_eps_by_year[year]
                if split_year and year < split_year:
                    adjusted_eps = raw_eps / split_adjustment_factor
                    eps_by_year[year] = adjusted_eps
                    logger.debug(f"[{symbol}] Split-adjusted EPS for {year}: ${raw_eps:.2f} -> ${adjusted_eps:.2f}")
                else:
                    eps_by_year[year] = raw_eps

        # Create mapping of year to Cash Flow for easy lookup
        cash_flow_by_year = {entry['year']: entry for entry in cash_flow_history}

        # Track years that need D/E data
        years_needing_de = []
        years_needing_cf = []

        # Store all revenue years (with or without net income)
        for rev_entry in revenue_history:
            year = rev_entry['year']
            revenue = rev_entry['revenue']
            fiscal_end = rev_entry.get('fiscal_end')
            debt_to_equity = debt_to_equity_by_year.get(year)
            shareholder_equity = shareholder_equity_by_year.get(year)
            eps = eps_by_year.get(year)
            dividend = dividends_by_year.get(year)

            # Get net income if available for this year
            ni_data = net_income_by_year.get(year)
            net_income = ni_data['net_income'] if ni_data else None
            # Prefer revenue's fiscal_end, fall back to NI's fiscal_end if available
            if not fiscal_end and ni_data:
                fiscal_end = ni_data.get('fiscal_end')

            # Get cash flow data
            cf_data = cash_flow_by_year.get(year, {})
            operating_cash_flow = cf_data.get('operating_cash_flow')
            capital_expenditures = cf_data.get('capital_expenditures')
            free_cash_flow = cf_data.get('free_cash_flow')

            # Determine missing CF data
            missing_cf = (operating_cash_flow is None or free_cash_flow is None)
            if missing_cf:
                 years_needing_cf.append(year)

            self.db.save_earnings_history(symbol, year, float(eps) if eps else None, float(revenue), fiscal_end=fiscal_end, debt_to_equity=debt_to_equity, net_income=float(net_income) if net_income else None, dividend_amount=float(dividend) if dividend is not None else None, operating_cash_flow=float(operating_cash_flow) if operating_cash_flow is not None else None, capital_expenditures=float(capital_expenditures) if capital_expenditures is not None else None, free_cash_flow=float(free_cash_flow) if free_cash_flow is not None else None, shareholder_equity=float(shareholder_equity) if shareholder_equity is not None else None)
            logger.debug(f"[{symbol}] Stored EDGAR for {year}: Revenue: ${revenue:,.0f}" + (f", NI: ${net_income:,.0f}" if net_income else " (no NI)") + (f", Div: ${dividend:.2f}" if dividend else "") + (f", FCF: ${free_cash_flow:,.0f}" if free_cash_flow else ""))

            # Track years missing D/E data
            if debt_to_equity is None:
                years_needing_de.append(year)

        # If EDGAR didn't provide D/E data, try to get it from yfinance
        if years_needing_de:
            logger.info(f"[{symbol}] EDGAR missing D/E for {len(years_needing_de)} years. Fetching from yfinance balance sheet")
            self._backfill_debt_to_equity(symbol, years_needing_de)

        if years_needing_cf:
            logger.info(f"[{symbol}] EDGAR missing Cash Flow for {len(years_needing_cf)} years. Fetching from yfinance cashflow")
            self._backfill_cash_flow(symbol, years_needing_cf)

    # todo: can this be collapsed with _store_edgar_earnings?
    def _store_edgar_quarterly_earnings(self, symbol: str, edgar_data: Dict[str, Any], price_history: Optional[pd.DataFrame] = None, force_refresh: bool = False):
        """Store quarterly earnings history from EDGAR data using Net Income"""
        # Use net_income_quarterly (raw quarterly Net Income from EDGAR)
        net_income_quarterly = edgar_data.get('net_income_quarterly', [])
        
        # Parse dividend history
        dividend_history = edgar_data.get('dividend_history', [])
        
        # Map dividends to (year, quarter)
        dividends_by_quarter = {}
        for div in dividend_history:
            if div.get('period') == 'quarterly' and div.get('quarter'):
                key = (div['year'], div['quarter'])
                dividends_by_quarter[key] = div['amount']

        if not net_income_quarterly:
            logger.warning(f"[{symbol}] No quarterly Net Income data available from EDGAR")
            return

        # Only clear existing quarterly data on force refresh
        # This allows the upsert to handle normal updates while ensuring
        # force refresh completely replaces potentially-bad historical data
        if force_refresh:
            self.db.clear_quarterly_earnings(symbol)

        quarters_stored = 0
        for entry in net_income_quarterly:
            year = entry['year']
            quarter = entry['quarter']
            net_income = entry.get('net_income')
            fiscal_end = entry.get('fiscal_end')
            
            dividend = dividends_by_quarter.get((year, quarter))

            if year and quarter and net_income:
                # Store with period like 'Q1', 'Q2', 'Q3', 'Q4'
                self.db.save_earnings_history(
                    symbol,
                    year,
                    None,  # No EPS for quarterly data
                    None,  # No revenue for quarterly data
                    fiscal_end=fiscal_end,
                    debt_to_equity=None,  # No D/E for quarterly data
                    period=quarter,
                    net_income=float(net_income),
                    dividend_amount=float(dividend) if dividend is not None else None
                )
                quarters_stored += 1

        logger.info(f"[{symbol}] Stored {quarters_stored} quarters of EDGAR Net Income data")

    def _backfill_debt_to_equity(self, symbol: str, years: List[int]):
        """
        Backfill missing debt-to-equity data from yfinance balance sheets

        Args:
            symbol: Stock symbol
            years: List of years that need D/E data
        """
        try:
            balance_sheet = self._get_yf_balance_sheet(symbol)

            if balance_sheet is None or balance_sheet.empty:
                logger.warning(f"[{symbol}] No balance sheet data available from yfinance")
                return

            de_filled_count = 0
            for col in balance_sheet.columns:
                year = col.year if hasattr(col, 'year') else None
                if year and year in years:
                    debt_to_equity, _ = self._calculate_debt_to_equity(balance_sheet, col)
                    if debt_to_equity is not None:
                        # Update the existing record with D/E data
                        conn = self.db.get_connection()
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE earnings_history
                                SET debt_to_equity = %s
                                WHERE symbol = %s AND year = %s AND period = 'annual'
                            """, (debt_to_equity, symbol, year))
                            conn.commit()
                            de_filled_count += 1
                            logger.debug(f"[{symbol}] Backfilled D/E for {year}: {debt_to_equity:.2f}")
                        finally:
                            self.db.return_connection(conn)

            if de_filled_count > 0:
                logger.info(f"[{symbol}] Successfully backfilled D/E for {de_filled_count}/{len(years)} years from yfinance")
            else:
                logger.debug(f"[{symbol}] Could not backfill any D/E data from yfinance")

        except Exception as e:
            logger.error(f"[{symbol}] Error backfilling D/E data: {type(e).__name__}: {e}")

    def _calculate_debt_to_equity(self, balance_sheet, col) -> tuple[Optional[float], Optional[float]]:
        """
        Calculate debt-to-equity ratio from balance sheet data

        Args:
            balance_sheet: pandas DataFrame containing balance sheet data
            col: column/date to extract data from

        Returns:
            Tuple of (debt_to_equity_ratio, total_debt) or (None, None) if data unavailable
        """
        try:
            # Try to get Total Debt (preferred) or Total Liabilities
            debt_or_liab = None
            equity = None

            # List of possible keys for Debt (preferred)
            # 'Total Debt' is explicit interest-bearing debt
            # 'Total Liabilities' includes everything (payables, deferred tax, etc.) and gives a much higher ratio
            debt_keys = [
                'Total Debt',
                'Total Liabilities Net Minority Interest',
                'Total Liab',
                'Total Liabilities',
                'Total Liabilities Net Minority Interest'
            ]

            for key in debt_keys:
                if key in balance_sheet.index:
                    debt_or_liab = balance_sheet.loc[key, col]
                    if pd.notna(debt_or_liab):
                        logger.debug(f"Using {key} for D/E calculation: {debt_or_liab}")
                        break

            # List of possible keys for Equity
            equity_keys = [
                'Stockholders Equity',
                'Total Stockholder Equity',
                'Total Equity Gross Minority Interest',
                'Common Stock Equity'
            ]

            for key in equity_keys:
                if key in balance_sheet.index:
                    equity = balance_sheet.loc[key, col]
                    break

            # Calculate D/E ratio if both values are available and valid
            if pd.notna(debt_or_liab) and pd.notna(equity) and equity != 0:
                ratio = float(debt_or_liab / equity)
                total_debt = float(debt_or_liab)
                return (ratio, total_debt)

            return (None, None)
        except Exception as e:
            logger.debug(f"Error calculating D/E ratio: {e}")
            return (None, None)

    def _backfill_cash_flow(self, symbol: str, years: List[int]):
        """
        Backfill missing cash flow data (OCF, CapEx, FCF) from yfinance
        """
        try:
            # We need the cashflow statement properly
            ticker = yf.Ticker(symbol)
            cashflow = ticker.cashflow
            
            if cashflow is None or cashflow.empty:
                logger.warning(f"[{symbol}] No cashflow data available from yfinance")
                return

            cf_filled_count = 0
            
            # Helper to safely get value from Series/DataFrame
            def get_val(df, keys):
                for key in keys:
                    if key in df.index:
                        return df.loc[key]
                return None

            for col in cashflow.columns:
                year = col.year if hasattr(col, 'year') else None
                if year and year in years:
                    # Extract metrics for this year
                    # Use standard yfinance keys
                    ocf = get_val(cashflow[col], ['Operating Cash Flow', 'Total Cash From Operating Activities'])
                    capex = get_val(cashflow[col], ['Capital Expenditure', 'Capital Expenditures', 'Total Capital Expenditures'])
                    fcf = get_val(cashflow[col], ['Free Cash Flow'])

                    # Prepare updates
                    updates = []
                    params = []

                    if ocf is not None and not pd.isna(ocf):
                        updates.append("operating_cash_flow = %s")
                        params.append(float(ocf))
                    
                    if capex is not None and not pd.isna(capex):
                        updates.append("capital_expenditures = %s")
                        # yfinance usually reports CapEx as negative, which aligns with our standard
                        params.append(float(capex))
                    
                    if fcf is not None and not pd.isna(fcf):
                        updates.append("free_cash_flow = %s")
                        params.append(float(fcf))

                    if updates:
                        conn = self.db.get_connection()
                        try:
                            cursor = conn.cursor()
                            # Construct dynamic UPDATE query
                            query = f"UPDATE earnings_history SET {', '.join(updates)} WHERE symbol = %s AND year = %s AND period = 'annual'"
                            params.extend([symbol, year])
                            
                            cursor.execute(query, tuple(params))
                            conn.commit()
                            cf_filled_count += 1
                            logger.debug(f"[{symbol}] Backfilled Cash Flow for {year}: OCF={ocf}, CapEx={capex}, FCF={fcf}")
                        finally:
                            self.db.return_connection(conn)
            
            if cf_filled_count > 0:
                logger.info(f"[{symbol}] Successfully backfilled Cash Flow for {cf_filled_count}/{len(years)} years from yfinance")
        except Exception as e:
            logger.error(f"[{symbol}] Error backfilling Cash Flow data: {e}")


    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance dividends")
    def _get_yf_dividends(self, symbol: str):
        """Fetch yfinance dividends with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.dividends

    def _fetch_and_store_earnings(self, symbol: str):
        try:
            # Fetch annual data with timeout protection
            financials = self._get_yf_financials(symbol)
            balance_sheet = self._get_yf_balance_sheet(symbol)
            cashflow = self._get_yf_cashflow(symbol)
            dividends = self._get_yf_dividends(symbol)
            price_history = self._get_yf_history(symbol)
            
            # Process dividends into annual sums
            dividends_by_year = {}
            if dividends is not None and not dividends.empty:
                # dividends is a Series with DateTime index
                for date, amount in dividends.items():
                    year = date.year
                    if year not in dividends_by_year:
                        dividends_by_year[year] = 0.0
                    dividends_by_year[year] += amount

            if financials is not None and not financials.empty:
                year_count = len(financials.columns)
                logger.info(f"[{symbol}] yfinance returned {year_count} years of annual data")

                if year_count < 5:
                    logger.warning(f"[{symbol}] Limited data: only {year_count} years available from yfinance")

                for col in financials.columns:
                    year = col.year if hasattr(col, 'year') else None
                    if not year:
                        continue

                    revenue = None
                    if 'Total Revenue' in financials.index:
                        revenue = financials.loc['Total Revenue', col]

                    eps = None
                    if 'Diluted EPS' in financials.index:
                        eps = financials.loc['Diluted EPS', col]

                    # Extract Net Income from yfinance financials
                    net_income = None
                    if 'Net Income' in financials.index:
                        net_income = financials.loc['Net Income', col]

                    # Calculate debt-to-equity from balance sheet
                    debt_to_equity = None
                    if balance_sheet is not None and not balance_sheet.empty and col in balance_sheet.columns:
                        debt_to_equity, _ = self._calculate_debt_to_equity(balance_sheet, col)
                    
                    dividend = dividends_by_year.get(year)

                    if year and pd.notna(revenue) and pd.notna(eps):
                        # Extract cash flow metrics
                        operating_cash_flow = None
                        capital_expenditures = None
                        free_cash_flow = None

                        if cashflow is not None and not cashflow.empty and col in cashflow.columns:
                            if 'Operating Cash Flow' in cashflow.index:
                                operating_cash_flow = cashflow.loc['Operating Cash Flow', col]
                            elif 'Total Cash From Operating Activities' in cashflow.index:
                                operating_cash_flow = cashflow.loc['Total Cash From Operating Activities', col]
                            
                            if 'Capital Expenditure' in cashflow.index:
                                capital_expenditures = cashflow.loc['Capital Expenditure', col]
                                # In yfinance, CapEx is usually negative. We want positive for storage (or consistent with EDGAR).
                                # EDGAR usually reports "Payments to Acquire..." which is positive number representing outflow.
                                # yfinance reports negative number. Let's flip it to positive to match "Payments..." concept?
                                # Actually, let's check EDGAR. EDGAR "NetCashProvidedByUsedIn..." is signed.
                                # "PaymentsToAcquire..." is usually positive in the tag, but contextually an outflow.
                                # Let's store signed values as they come from source, but be careful with FCF calc.
                                # yfinance: OCF is positive, CapEx is negative. FCF = OCF + CapEx.
                                # EDGAR: OCF is positive/negative. CapEx we extracted as "Payments...", usually positive.
                                # In parse_cash_flow_history we did FCF = OCF - CapEx.
                                # So for yfinance, if CapEx is negative, we should probably flip it to positive to match "Payments" concept
                                # OR just store it as is and handle it.
                                # Let's try to standardize: Store CapEx as a positive number representing the cost.
                                if capital_expenditures is not None and capital_expenditures < 0:
                                    capital_expenditures = -capital_expenditures
                            
                            if 'Free Cash Flow' in cashflow.index:
                                free_cash_flow = cashflow.loc['Free Cash Flow', col]
                            elif operating_cash_flow is not None and capital_expenditures is not None:
                                free_cash_flow = operating_cash_flow - capital_expenditures

                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period='annual',
                                                     net_income=float(net_income) if pd.notna(net_income) else None,
                                                     dividend_amount=float(dividend) if dividend is not None else None,
                                                     operating_cash_flow=float(operating_cash_flow) if operating_cash_flow is not None else None,
                                                     capital_expenditures=float(capital_expenditures) if capital_expenditures is not None else None,
                                                     free_cash_flow=float(free_cash_flow) if free_cash_flow is not None else None)

            # Fetch quarterly data with timeout protection
            quarterly_financials = self._get_yf_quarterly_financials(symbol)
            quarterly_balance_sheet = self._get_yf_quarterly_balance_sheet(symbol)

            if quarterly_financials is not None and not quarterly_financials.empty:
                quarter_count = len(quarterly_financials.columns)
                logger.info(f"[{symbol}] yfinance returned {quarter_count} quarters of data")

                for col in quarterly_financials.columns:
                    year = col.year if hasattr(col, 'year') else None
                    quarter = col.quarter if hasattr(col, 'quarter') else None

                    if not year or not quarter:
                        continue

                    revenue = None
                    if 'Total Revenue' in quarterly_financials.index:
                        revenue = quarterly_financials.loc['Total Revenue', col]

                    eps = None
                    if 'Diluted EPS' in quarterly_financials.index:
                        eps = quarterly_financials.loc['Diluted EPS', col]

                    # Extract Net Income from quarterly financials
                    net_income = None
                    if 'Net Income' in quarterly_financials.index:
                        net_income = quarterly_financials.loc['Net Income', col]

                    # Calculate debt-to-equity from quarterly balance sheet
                    debt_to_equity = None
                    if quarterly_balance_sheet is not None and not quarterly_balance_sheet.empty and col in quarterly_balance_sheet.columns:
                        debt_to_equity, _ = self._calculate_debt_to_equity(quarterly_balance_sheet, col)
                    
                    # Map dividends to (year, quarter)
                    # Note: We need to calculate dividends_by_quarter here or reuse from above if we move it up
                    # Since we didn't calculate it in this method yet, let's do it now
                    dividends_by_quarter = {}
                    if dividends is not None and not dividends.empty:
                        for date, amount in dividends.items():
                            year = date.year
                            month = date.month
                            quarter = (month - 1) // 3 + 1
                            key = (year, quarter)
                            if key not in dividends_by_quarter:
                                dividends_by_quarter[key] = 0.0
                            dividends_by_quarter[key] += amount
                    
                    dividend = dividends_by_quarter.get((year, quarter))

                    if year and quarter and pd.notna(revenue) and pd.notna(eps):
                        period = f'Q{quarter}'
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period=period,
                                                     net_income=float(net_income) if pd.notna(net_income) else None,
                                                     dividend_amount=float(dividend) if dividend is not None else None)

        except Exception as e:
            logger.error(f"[{symbol}] Error fetching earnings from yfinance: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def _fetch_quarterly_earnings(self, symbol: str):
        """Fetch and store ONLY quarterly earnings data from yfinance"""
        try:
            # Fetch quarterly data only with timeout protection
            quarterly_financials = self._get_yf_quarterly_financials(symbol)
            quarterly_balance_sheet = self._get_yf_quarterly_balance_sheet(symbol)
            dividends = self._get_yf_dividends(symbol)
            price_history = self._get_yf_history(symbol)
            
            # Map dividends to (year, quarter)
            dividends_by_quarter = {}
            if dividends is not None and not dividends.empty:
                for date, amount in dividends.items():
                    year = date.year
                    month = date.month
                    # Estimate quarter based on month
                    quarter = (month - 1) // 3 + 1
                    key = (year, quarter)
                    if key not in dividends_by_quarter:
                        dividends_by_quarter[key] = 0.0
                    dividends_by_quarter[key] += amount

            if quarterly_financials is not None and not quarterly_financials.empty:
                quarter_count = len(quarterly_financials.columns)
                logger.info(f"[{symbol}] yfinance returned {quarter_count} quarters of data")

                for col in quarterly_financials.columns:
                    year = col.year if hasattr(col, 'year') else None
                    quarter = col.quarter if hasattr(col, 'quarter') else None

                    if not year or not quarter:
                        continue

                    revenue = None
                    if 'Total Revenue' in quarterly_financials.index:
                        revenue = quarterly_financials.loc['Total Revenue', col]

                    eps = None
                    if 'Diluted EPS' in quarterly_financials.index:
                        eps = quarterly_financials.loc['Diluted EPS', col]

                    # Extract Net Income from quarterly financials
                    net_income = None
                    if 'Net Income' in quarterly_financials.index:
                        net_income = quarterly_financials.loc['Net Income', col]

                    # Calculate debt-to-equity from quarterly balance sheet
                    debt_to_equity = None
                    if quarterly_balance_sheet is not None and not quarterly_balance_sheet.empty and col in quarterly_balance_sheet.columns:
                        debt_to_equity, _ = self._calculate_debt_to_equity(quarterly_balance_sheet, col)
                    
                    dividend = dividends_by_quarter.get((year, quarter))

                    if year and quarter and pd.notna(revenue) and pd.notna(eps):
                        period = f'Q{quarter}'
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period=period,
                                                     net_income=float(net_income) if pd.notna(net_income) else None,
                                                     dividend_amount=float(dividend) if dividend is not None else None)
            else:
                logger.warning(f"[{symbol}] No quarterly financial data available from yfinance")

        except Exception as e:
            logger.error(f"[{symbol}] Error fetching quarterly earnings from yfinance: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def fetch_multiple_stocks(self, symbols: List[str], force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        results = {}
        for symbol in symbols:
            data = self.fetch_stock_data(symbol, force_refresh)
            if data:
                results[symbol] = data
        return results

    @retry_on_rate_limit(max_retries=3, initial_delay=2.0)
    def get_nyse_nasdaq_symbols(self) -> List[str]:
        """
        Get NYSE and NASDAQ symbols with database caching.
        Cache expires after 24 hours.
        Uses NASDAQ's official FTP server instead of GitHub.
        """
        # Check cache first
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Create cache table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbol_cache (
                    id INTEGER PRIMARY KEY,
                    symbols TEXT,
                    last_updated TIMESTAMP
                )
            """)

            # Migration: ensure symbol_cache.id has primary key (for existing databases)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints
                                   WHERE table_name = 'symbol_cache' AND constraint_type = 'PRIMARY KEY') THEN
                        ALTER TABLE symbol_cache ADD PRIMARY KEY (id);
                    END IF;
                END $$;
            """)

            # Check if we have recent cached symbols (less than 24 hours old)
            cursor.execute("""
                SELECT symbols, last_updated FROM symbol_cache
                WHERE id = 1 AND last_updated > NOW() - INTERVAL '24 hours'
            """)
            cached = cursor.fetchone()

            if cached:
                symbols = cached[0].split(',')
                print(f"Using cached symbol list ({len(symbols)} symbols, last updated: {cached[1]})")
                return symbols

            # Fetch fresh symbols from NASDAQ FTP
            print("Fetching fresh symbol list from NASDAQ FTP...")
            
            # NASDAQ's official FTP - includes both NASDAQ and NYSE listed stocks
            nasdaq_url = "ftp://ftp.nasdaqtrader.com/symboldirectory/nasdaqlisted.txt"
            other_url = "ftp://ftp.nasdaqtrader.com/symboldirectory/otherlisted.txt"
            
            # Read NASDAQ-listed stocks
            nasdaq_df = pd.read_csv(nasdaq_url, sep='|')
            nasdaq_symbols = nasdaq_df['Symbol'].tolist()
            
            # Read other exchanges (NYSE, AMEX, etc.)
            other_df = pd.read_csv(other_url, sep='|')
            other_symbols = other_df['ACT Symbol'].tolist()
            
            # Combine and clean
            all_symbols = list(set(nasdaq_symbols + other_symbols))
            all_symbols = [s.strip() for s in all_symbols if isinstance(s, str) and s.strip()]
            
            # Filter out test symbols and file trailer markers
            all_symbols = [s for s in all_symbols if not s.startswith('File') and len(s) <= 5]
            all_symbols = sorted(all_symbols)
            
            # Update cache
            cursor.execute("""
                INSERT INTO symbol_cache (id, symbols, last_updated)
                VALUES (1, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    symbols = EXCLUDED.symbols,
                    last_updated = EXCLUDED.last_updated
            """, (','.join(all_symbols),))
            conn.commit()

            print(f"Cached {len(all_symbols)} symbols from NASDAQ FTP")
            return all_symbols

        except Exception as e:
            print(f"Error fetching stock symbols from NASDAQ: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()

            # If fetch fails, try to return stale cache as fallback
            try:
                cursor.execute("SELECT symbols FROM symbol_cache WHERE id = 1")
                stale_cached = cursor.fetchone()

                if stale_cached:
                    symbols = stale_cached[0].split(',')
                    print(f"Using stale cached symbols as fallback ({len(symbols)} symbols)")
                    return symbols
            except:
                pass

            return []
        finally:
            self.db.return_connection(conn)
