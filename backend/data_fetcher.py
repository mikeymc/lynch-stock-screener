# ABOUTME: Fetches stock data using hybrid EDGAR + yfinance approach
# ABOUTME: Uses EDGAR for fundamentals, yfinance for current market data

import yfinance as yf
import logging
from typing import Dict, Any, Optional, List
from database import Database
from edgar_fetcher import EdgarFetcher
import pandas as pd

logger = logging.getLogger(__name__)


class DataFetcher:
    def __init__(self, db: Database):
        self.db = db
        self.edgar_fetcher = EdgarFetcher(user_agent="Lynch Stock Screener mikey@example.com")

    def fetch_stock_data(self, symbol: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        if not force_refresh and self.db.is_cache_valid(symbol):
            return self.db.get_stock_metrics(symbol)

        try:
            # Try fetching fundamentals from EDGAR first
            logger.info(f"[{symbol}] Attempting EDGAR fetch")
            edgar_data = self.edgar_fetcher.fetch_stock_fundamentals(symbol)

            # Fetch current market data from yfinance
            stock = yf.Ticker(symbol)
            info = stock.info

            if not info or 'symbol' not in info:
                return None

            company_name = info.get('longName', '')
            exchange = info.get('exchange', '')
            sector = info.get('sector', '')
            country = info.get('country', '')

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

            self.db.save_stock_basic(symbol, company_name, exchange, sector, country, ipo_year)

            # Use EDGAR debt-to-equity if available, otherwise fall back to yfinance
            debt_to_equity = None
            if edgar_data and edgar_data.get('debt_to_equity'):
                debt_to_equity = edgar_data['debt_to_equity']
            else:
                debt_to_equity_pct = info.get('debtToEquity', 0)
                debt_to_equity = debt_to_equity_pct / 100 if debt_to_equity_pct else None

            # Use yfinance for current market data (price, P/E, market cap, institutional ownership)
            metrics = {
                'price': info.get('currentPrice'),
                'pe_ratio': info.get('trailingPE'),
                'market_cap': info.get('marketCap'),
                'debt_to_equity': debt_to_equity,
                'institutional_ownership': info.get('heldPercentInstitutions'),
                'revenue': info.get('totalRevenue')
            }
            self.db.save_stock_metrics(symbol, metrics)

            # Use EDGAR earnings history if available, otherwise fall back to yfinance
            if edgar_data and edgar_data.get('eps_history') and edgar_data.get('revenue_history'):
                eps_count = len(edgar_data.get('eps_history', []))
                rev_count = len(edgar_data.get('revenue_history', []))

                # Calculate how many matched years we'll get
                eps_years = {entry['year'] for entry in edgar_data.get('eps_history', [])}
                rev_years = {entry['year'] for entry in edgar_data.get('revenue_history', [])}
                matched_years = len(eps_years & rev_years)

                logger.info(f"[{symbol}] EDGAR returned {eps_count} EPS years, {rev_count} revenue years, {matched_years} matched")

                # Use EDGAR only if we have >= 5 matched years, otherwise fall back to yfinance
                if matched_years >= 5:
                    logger.info(f"[{symbol}] Using EDGAR data ({matched_years} years)")
                    self._store_edgar_earnings(symbol, edgar_data)
                else:
                    logger.info(f"[{symbol}] EDGAR has insufficient matched years ({matched_years} < 5). Falling back to yfinance")
                    self._fetch_and_store_earnings(symbol, stock)
            else:
                if edgar_data:
                    eps_count = len(edgar_data.get('eps_history', []))
                    rev_count = len(edgar_data.get('revenue_history', []))
                    logger.info(f"[{symbol}] Partial EDGAR data: {eps_count} EPS years, {rev_count} revenue years. Falling back to yfinance")
                else:
                    logger.info(f"[{symbol}] EDGAR fetch failed. Using yfinance")
                self._fetch_and_store_earnings(symbol, stock)

            return self.db.get_stock_metrics(symbol)

        except Exception as e:
            print(f"Error fetching stock data for {symbol}: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def _store_edgar_earnings(self, symbol: str, edgar_data: Dict[str, Any]):
        """Store earnings history from EDGAR data"""
        eps_history = edgar_data.get('eps_history', [])
        revenue_history = edgar_data.get('revenue_history', [])

        # Create mapping of year to revenue and fiscal_end for easy lookup
        revenue_by_year = {entry['year']: {'revenue': entry['revenue'], 'fiscal_end': entry.get('fiscal_end')} for entry in revenue_history}

        # Store each year's data
        for eps_entry in eps_history:
            year = eps_entry['year']
            eps = eps_entry['eps']
            fiscal_end = eps_entry.get('fiscal_end')
            revenue_data = revenue_by_year.get(year)

            if year and eps and revenue_data:
                revenue = revenue_data['revenue']
                # Prefer revenue's fiscal_end if available, otherwise use EPS's fiscal_end
                final_fiscal_end = revenue_data.get('fiscal_end') or fiscal_end
                self.db.save_earnings_history(symbol, year, float(eps), float(revenue), fiscal_end=final_fiscal_end)

    def _fetch_and_store_earnings(self, symbol: str, stock):
        try:
            financials = stock.financials
            if financials is not None and not financials.empty:
                year_count = len(financials.columns)
                logger.info(f"[{symbol}] yfinance returned {year_count} years of data")

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

                    if year and pd.notna(revenue) and pd.notna(eps):
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue))
        except Exception as e:
            logger.error(f"[{symbol}] Error fetching earnings from yfinance: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def fetch_multiple_stocks(self, symbols: List[str], force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        results = {}
        for symbol in symbols:
            data = self.fetch_stock_data(symbol, force_refresh)
            if data:
                results[symbol] = data
        return results

    def get_nyse_nasdaq_symbols(self) -> List[str]:
        try:
            nyse_url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nyse/nyse_tickers.txt"
            nasdaq_url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nasdaq/nasdaq_tickers.txt"

            nyse_symbols = pd.read_csv(nyse_url, header=None)[0].tolist()
            nasdaq_symbols = pd.read_csv(nasdaq_url, header=None)[0].tolist()

            all_symbols = list(set(nyse_symbols + nasdaq_symbols))

            all_symbols = [s for s in all_symbols if isinstance(s, str)]

            return sorted(all_symbols)
        except Exception as e:
            print(f"Error fetching stock symbols: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
