# ABOUTME: Fetches stock data using hybrid EDGAR + yfinance approach
# ABOUTME: Uses EDGAR for fundamentals, yfinance for current market data

import yfinance as yf
from typing import Dict, Any, Optional, List
from database import Database
from edgar_fetcher import EdgarFetcher
import pandas as pd


class DataFetcher:
    def __init__(self, db: Database):
        self.db = db
        self.edgar_fetcher = EdgarFetcher(user_agent="Lynch Stock Screener mikey@example.com")

    def fetch_stock_data(self, symbol: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        if not force_refresh and self.db.is_cache_valid(symbol):
            return self.db.get_stock_metrics(symbol)

        try:
            # Try fetching fundamentals from EDGAR first
            edgar_data = self.edgar_fetcher.fetch_stock_fundamentals(symbol)

            # Fetch current market data from yfinance
            stock = yf.Ticker(symbol)
            info = stock.info

            if not info or 'symbol' not in info:
                return None

            company_name = info.get('longName', '')
            exchange = info.get('exchange', '')
            sector = info.get('sector', '')

            self.db.save_stock_basic(symbol, company_name, exchange, sector)

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
                self._store_edgar_earnings(symbol, edgar_data)
            else:
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

        # Create mapping of year to revenue for easy lookup
        revenue_by_year = {entry['year']: entry['revenue'] for entry in revenue_history}

        # Store each year's data
        for eps_entry in eps_history:
            year = eps_entry['year']
            eps = eps_entry['eps']
            revenue = revenue_by_year.get(year)

            if year and eps and revenue:
                self.db.save_earnings_history(symbol, year, float(eps), float(revenue))

    def _fetch_and_store_earnings(self, symbol: str, stock):
        try:
            financials = stock.financials
            if financials is not None and not financials.empty:
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
        except Exception:
            pass

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
