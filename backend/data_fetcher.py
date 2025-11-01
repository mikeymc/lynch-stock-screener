# ABOUTME: Fetches stock data from yfinance API with database caching
# ABOUTME: Handles data retrieval, parsing, and storage for NYSE/NASDAQ stocks

import yfinance as yf
from typing import Dict, Any, Optional, List
from database import Database
import pandas as pd


class DataFetcher:
    def __init__(self, db: Database):
        self.db = db

    def fetch_stock_data(self, symbol: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        if not force_refresh and self.db.is_cache_valid(symbol):
            return self.db.get_stock_metrics(symbol)

        try:
            stock = yf.Ticker(symbol)
            info = stock.info

            if not info or 'symbol' not in info:
                return None

            company_name = info.get('longName', '')
            exchange = info.get('exchange', '')
            sector = info.get('sector', '')

            self.db.save_stock_basic(symbol, company_name, exchange, sector)

            debt_to_equity_pct = info.get('debtToEquity', 0)
            debt_to_equity = debt_to_equity_pct / 100 if debt_to_equity_pct else None

            metrics = {
                'price': info.get('currentPrice'),
                'pe_ratio': info.get('trailingPE'),
                'market_cap': info.get('marketCap'),
                'debt_to_equity': debt_to_equity,
                'institutional_ownership': info.get('heldPercentInstitutions'),
                'revenue': info.get('totalRevenue')
            }
            self.db.save_stock_metrics(symbol, metrics)

            self._fetch_and_store_earnings(symbol, stock)

            return self.db.get_stock_metrics(symbol)

        except Exception as e:
            return None

    def _fetch_and_store_earnings(self, symbol: str, stock):
        try:
            financials = stock.financials
            if financials is not None and not financials.empty:
                for col in financials.columns:
                    if 'Total Revenue' in financials.index:
                        year = col.year if hasattr(col, 'year') else None
                        revenue = financials.loc['Total Revenue', col]
                        if year and pd.notna(revenue):
                            eps = 0.0
                            self.db.save_earnings_history(symbol, year, eps, float(revenue))
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
