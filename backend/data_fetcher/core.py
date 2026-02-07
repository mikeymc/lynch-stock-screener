# ABOUTME: Core DataFetcher class with stock data fetching, yfinance helpers, and symbol listing
# ABOUTME: Contains __init__, yf wrapper methods, fetch_stock_data entry point, and retry decorator

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
from earnings_extractor import EarningsExtractor
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



class DataFetcherCore:
    def __init__(self, db: Database):
        self.db = db
        # Pass database instance to EdgarFetcher (it will get/return connections as needed)
        self.edgar_fetcher = EdgarFetcher(
            user_agent="Lynch Stock Screener mikey@example.com",
            db=db
        )
        self.earnings_extractor = EarningsExtractor()

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
                    'regularMarketChangePercent': cached_data.get('price_change_pct'),
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
                    'totalRevenue': cached_data.get('total_revenue'),
                    'totalDebt': cached_data.get('total_debt'),
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

            # Fallback: If not in Finviz cache, try yfinance
            # Even if using_tradingview_cache is True, we might need to fetch this if it's important
            if institutional_ownership is None:
                if info.get('heldPercentInstitutions') is not None:
                     institutional_ownership = info.get('heldPercentInstitutions')
                elif using_tradingview_cache:
                     # If we really need it and don't have it, we might consider a quick fetch
                     # But yfinance info is slow. Let's try to get it from yf_info only if we fetch it for other reasons
                     # OR just accept None for speed.
                     pass

            if institutional_ownership is None and not using_tradingview_cache:
                 logger.debug(f"[{symbol}] Institutional ownership missing from both Finviz and yfinance")

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

            # Get interest expense - prefer EDGAR data, then yfinance
            interest_expense = None
            if edgar_data and edgar_data.get('interest_expense'):
                interest_expense = edgar_data['interest_expense']
                logger.info(f"[{symbol}] Using EDGAR Interest Expense: ${interest_expense:,.0f}")

            # Get effective tax rate - prefer EDGAR data
            effective_tax_rate = None
            if edgar_data and edgar_data.get('effective_tax_rate'):
                 effective_tax_rate = edgar_data['effective_tax_rate']
                 logger.info(f"[{symbol}] Using EDGAR Effective Tax Rate: {effective_tax_rate:.2%}")

            # Extract Revenue from EDGAR if missing from info (TradingView cache sets it to None)
            revenue = info.get('totalRevenue')
            if not revenue and edgar_data and edgar_data.get('revenue_history'):
                 # Get most recent annual revenue
                 latest_rev = edgar_data['revenue_history'][0] # sorted descending
                 revenue = latest_rev['revenue']
                 logger.info(f"[{symbol}] Using EDGAR Revenue: ${revenue:,.0f}")


            if not using_tradingview_cache:
                # Only fetch these slow yfinance calls if NOT using TradingView cache
                try:
                    ticker = yf.Ticker(symbol)
                    financials = ticker.financials
                    if financials is not None and not financials.empty:
                        # Only fetch if not already found from EDGAR
                        if interest_expense is None and 'Interest Expense' in financials.index:
                            interest_expense = abs(financials.loc['Interest Expense'].iloc[0])
                except Exception as e:
                    logger.debug(f"Could not fetch interest expense for {symbol}: {e}")

                # Calculate effective tax rate from income statement
                if effective_tax_rate is None:
                    try:
                        if financials is not None and not financials.empty:
                            if 'Tax Provision' in financials.index and 'Pretax Income' in financials.index:
                                tax = financials.loc['Tax Provision'].iloc[0]
                                pretax = financials.loc['Pretax Income'].iloc[0]
                                if pretax and pretax > 0:
                                    effective_tax_rate = tax / pretax
                    except Exception as e:
                        logger.debug(f"Could not calculate tax rate for {symbol}: {e}")

            # Calculate Gross Margin (for Buffett scoring)
            # Always calculate this regardless of cache since it's critical for Buffett scoring
            gross_margin = None
            try:
                ticker = yf.Ticker(symbol)
                income_stmt = ticker.income_stmt

                if income_stmt is not None and not income_stmt.empty:
                    # Look for gross profit and revenue
                    gross_profit = None
                    revenue = None

                    for key in ['Gross Profit', 'GrossProfit']:
                        if key in income_stmt.index:
                            gross_profit = income_stmt.loc[key].iloc[0]
                            break

                    for key in ['Total Revenue', 'TotalRevenue', 'Revenue']:
                        if key in income_stmt.index:
                            revenue = income_stmt.loc[key].iloc[0]
                            break

                    if gross_profit is not None and revenue is not None and revenue > 0:
                        gross_margin = (gross_profit / revenue) * 100  # as percentage
                        logger.info(f"[{symbol}] Calculated gross margin: {gross_margin:.2f}%")
            except Exception as e:
                logger.warning(f"[{symbol}] Could not calculate gross margin: {e}")

            metrics = {
                'price': info.get('currentPrice'),
                'price_change_pct': info.get('regularMarketChangePercent'),
                'pe_ratio': info.get('trailingPE'),
                'market_cap': info.get('marketCap'),
                'debt_to_equity': debt_to_equity,
                'institutional_ownership': institutional_ownership,
                'revenue': revenue,
                'dividend_yield': dividend_yield,
                'beta': beta,
                'total_debt': total_debt,
                'interest_expense': interest_expense,
                'effective_tax_rate': effective_tax_rate,
                'gross_margin': gross_margin,
                # New Future Indicators
                'forward_pe': info.get('forwardPE'),
                'forward_peg_ratio': info.get('pegRatio') if info.get('pegRatio') else info.get('trailingPegRatio'), # Prefer 5yr exepcted, fallback to trailing
                'forward_eps': info.get('forwardEps'),
                'short_ratio': info.get('shortRatio'),
                'short_percent_float': info.get('shortPercentOfFloat'),
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
                    # Smart Fallback: Allow yfinance fetch during screening for companies > $2B
                    # This catches recent major IPOs (like FIG) that lack 5-year EDGAR history
                    market_cap = metrics.get('market_cap')
                    if market_cap and market_cap > 2_000_000_000:
                        logger.info(f"[{symbol}] Significant Market Cap ({market_cap/1e9:.1f}B) missing EDGAR data - forcing yfinance fallback")
                        self._fetch_and_store_earnings(symbol)
                    else:
                        logger.info(f"[{symbol}] Skipping yfinance fallback (using TradingView cache)")


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
