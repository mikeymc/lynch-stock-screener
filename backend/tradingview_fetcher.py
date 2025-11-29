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
    
    def fetch_all_stocks(self, limit: int = 10000, regions: List[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Fetch market data for all stocks from TradingView
        
        Args:
            limit: Maximum number of stocks to fetch per region (default: 10000)
            regions: List of regions to fetch ('us', 'europe', 'asia'). If None, fetches all.
            
        Returns:
            Dictionary mapping symbol to market data
        """
        if regions is None:
            regions = ['us', 'europe', 'asia']
        
        # Define markets by region (TradingView market codes)
        # Note: 'america' includes NYSE, NASDAQ, AMEX
        # Excludes: India, China, Mexico, South America to reduce costs
        market_groups = {
            'us': ['america', 'canada'],  # US + Canada
            'europe': ['uk', 'germany', 'france', 'italy', 'spain', 'switzerland', 'netherlands', 'belgium', 'sweden'],
            'asia': ['hongkong', 'japan', 'korea', 'singapore', 'taiwan']  # Excludes India & China
        }
        
        all_results = {}
        
        for region in regions:
            if region not in market_groups:
                logger.warning(f"Unknown region: {region}, skipping")
                continue
                
            markets = market_groups[region]
            print(f"Fetching {region.upper()} stocks from markets: {', '.join(markets)}...")
            
            for market in markets:
                try:
                    # Build query for specific market
                    q = (Query()
                         .set_markets(market)
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
                             'exchange',                      # Exchange
                             'country',                       # Country
                             'currency',                      # Currency
                         )
                         .where(
                             # Filter to stocks with market cap > $1M
                             Column('market_cap_basic') > 1_000_000
                         )
                         .order_by('market_cap_basic', ascending=False)
                         .limit(limit)
                    )
                    
                    # Fetch data (returns count and DataFrame)
                    count, df = q.get_scanner_data()
                    
                    print(f"  ✓ {market}: {len(df)} stocks")
                    
                    # Convert DataFrame to dictionary keyed by ticker
                    for _, row in df.iterrows():
                        ticker = row.get('name')
                        if not ticker:
                            continue
                        
                        # Skip duplicates
                        if ticker not in all_results:
                            all_results[ticker] = self._normalize_row(row)
                    
                except Exception as e:
                    logger.error(f"Error fetching {market} stocks: {e}")
                    continue
        
        print(f"✓ Total unique stocks fetched: {len(all_results)}")
        return all_results
    
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
            'exchange': row.get('exchange'),
            'country': row.get('country'),  # May be None, will be filled by yfinance
            'currency': row.get('currency'),
            
            # Keep raw data for debugging
            '_raw': row.to_dict()
        }
