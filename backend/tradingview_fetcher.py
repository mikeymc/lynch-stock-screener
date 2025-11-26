"""
TradingView Screener API Fetcher

Fetches market data for all stocks using TradingView's screener API.
Much faster than individual yfinance calls - gets all data in a few requests.

Performance: ~10-20 requests for 10K stocks vs 10K individual requests.
"""

from tradingview_screener import Query, Column
import logging
from typing import Dict, Any, List
import pandas as pd

logger = logging.getLogger(__name__)


class TradingViewFetcher:
    """Fetches market data in bulk from TradingView screener API"""
    
    def __init__(self):
        """Initialize TradingView fetcher"""
        pass
    
    def fetch_all_stocks(self, limit: int = 10000) -> Dict[str, Dict[str, Any]]:
        """
        Fetch market data for all stocks from TradingView
        
        Args:
            limit: Maximum number of stocks to fetch (default: 10000)
            
        Returns:
            Dictionary mapping symbol to market data:
            {
                'AAPL': {
                    'price': 150.25,
                    'market_cap': 2500000000000,
                    'pe_ratio': 28.5,
                    'dividend_yield': 0.0055,
                    'beta': 1.2,
                    'sector': 'Technology',
                    'institutional_ownership': 0.65
                },
                ...
            }
        """
        print(f"Fetching market data for up to {limit} stocks from TradingView...")
        
        try:
            # Build query with all needed fields
            q = (Query()
                 .select(
                     'name',                          # Ticker symbol
                     'description',                   # Company Name
                     'close',                         # Current price
                     'volume',                        # Volume
                     'market_cap_basic',              # Market cap
                     'price_earnings_ttm',            # P/E ratio (TTM)
                     'dividend_yield_recent',         # Dividend yield
                     'beta_1_year',                   # Beta
                     'earnings_per_share_basic_ttm',  # EPS
                     'sector',                        # Sector
                     'industry',                      # Industry
                     'number_of_employees',           # Employees
                 )
                 .where(
                     # Filter to US stocks with market cap > $1M
                     Column('market_cap_basic') > 1_000_000,
                     Column('exchange').isin(['NYSE', 'NASDAQ', 'AMEX'])
                 )
                 .order_by('market_cap_basic', ascending=False)
                 .limit(limit)
            )
            
            # Fetch data (returns count and DataFrame)
            count, df = q.get_scanner_data()
            
            print(f"✓ Fetched data for {len(df)} stocks from TradingView")
            
            # Convert DataFrame to dictionary keyed by ticker
            result = {}
            for _, row in df.iterrows():
                ticker = row.get('name')
                if not ticker:
                    continue
                
                result[ticker] = self._normalize_row(row)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching from TradingView: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _normalize_row(self, row: pd.Series) -> Dict[str, Any]:
        """
        Convert TradingView row to our schema
        
        Args:
            row: Pandas Series with TradingView data
            
        Returns:
            Normalized data dictionary
        """
        return {
            'symbol': row.get('name'),
            'company_name': row.get('description'),
            'price': row.get('close'),
            'market_cap': row.get('market_cap_basic'),
            'pe_ratio': row.get('price_earnings_ttm'),
            'dividend_yield': row.get('dividend_yield_recent'),
            'beta': row.get('beta_1_year'),
            'eps': row.get('earnings_per_share_basic_ttm'),
            'sector': row.get('sector'),
            'industry': row.get('industry'),
            'volume': row.get('volume'),
            'employees': row.get('number_of_employees'),
            
            # Keep raw data for debugging
            '_raw': row.to_dict()
        }
