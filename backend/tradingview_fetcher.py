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
    
    # European exchanges that primarily list US ADRs and foreign duplicates
    # These should be filtered to avoid duplicate analysis of US companies
    EUROPEAN_ADR_EXCHANGES = {
        'MIL',      # Milan (Italy) - lists US ADRs with numeric prefixes like 1AAPL
        'EUROTLX',  # EuroTLX - lists US ADRs like 4AAPL
        'LSX',      # London Stock Exchange International - lists US ADRs
        'LSE',      # London Stock Exchange - lists US ADRs with codes like 0QZ6
        'BX',       # XETRA (Germany) - lists US ADRs
        'DUS',      # Düsseldorf (Germany) - lists US ADRs
        'FWB',      # Frankfurt - lists US ADRs
        'STU',      # Stuttgart - lists US ADRs
        'MUN',      # Munich - lists US ADRs
        'HAM',      # Hamburg - lists US ADRs
        'BER',      # Berlin - lists US ADRs
        'LSIN',     # London Stock Exchange International
        'LS',       # Lang & Schwarz (Germany) - lists US ADRs
        'HAN',      # Hannover (Germany) - lists US ADRs
        'SWB',      # Stuttgart (Germany) - lists US ADRs
        'XETR',     # XETRA (Germany) - lists US ADRs
        'GETTEX',   # Gettex (Germany) - lists US ADRs
        'TRADEGATE', # Tradegate (Germany) - lists US ADRs
    }
    
    # OTC/Pink Sheet exchanges - these stocks often have no reliable price data
    OTC_EXCHANGES = {
        'OTC',      # OTC Markets
        'OTCQB',    # OTCQB Venture Market
        'OTCQX',    # OTCQX Best Market
        'PINK',     # Pink Sheets
        'GREY',     # Grey Market
    }
    
    # Asian home exchanges where numeric tickers are legitimate
    # These should NOT be filtered as they represent primary listings
    ASIAN_HOME_EXCHANGES = {
        'KRX',      # Korea Exchange - Korean stocks use numeric tickers (e.g., 000660 for SK hynix)
        'TWSE',     # Taiwan Stock Exchange - Taiwanese stocks use numeric tickers
        'HKEX',     # Hong Kong Exchange - Some HK stocks use numeric tickers
        'TSE',      # Tokyo Stock Exchange
        'SGX',      # Singapore Exchange
    }
    
    # Typespecs to include (common stocks and REITs)
    # Excludes: etf, preferred, unit, closedend, trust, dr (depositary receipts)
    ALLOWED_TYPESPECS = {'common', 'reit'}
    
    def __init__(self):
        """Initialize TradingView fetcher"""
        pass
    
    def _should_skip_ticker(self, ticker: str, exchange: str) -> bool:
        """
        Determine if a ticker should be filtered out (Hybrid Approach)
        
        Strategy:
        1. Filter out tickers from European ADR exchanges (avoid US company duplicates)
        2. Filter out non-common stock securities (preferred, warrants, units, etc.)
        3. Allow numeric tickers from Asian home exchanges (legitimate local stocks)
        4. Allow all other common stock tickers
        
        Args:
            ticker: Stock ticker symbol
            exchange: Exchange code from TradingView
            
        Returns:
            True if ticker should be skipped, False otherwise
        """
        if not ticker or not exchange:
            return True
        
        # Skip tickers from European ADR exchanges
        if exchange in self.EUROPEAN_ADR_EXCHANGES:
            logger.debug(f"Filtering {ticker} from European ADR exchange {exchange}")
            return True
        
        # Skip tickers from OTC/Pink Sheet exchanges (unreliable price data)
        if exchange in self.OTC_EXCHANGES:
            logger.debug(f"Filtering {ticker} from OTC exchange {exchange}")
            return True
        
        # Filter out non-common stock securities by ticker pattern
        ticker_upper = ticker.upper()
        
        # Preferred stock patterns with separators: -P, -PR, .PR, /PR, _PR
        # (Fallback for any preferred stocks not caught by typespecs filter)
        if any(ticker_upper.endswith(suffix) for suffix in ['-P', '-PR', '.PR', '/PR', '_PR']):
            logger.debug(f"Filtering preferred stock: {ticker}")
            return True
        
        # Warrant patterns: -W, -WT, .W, .WT, /W, _W
        if any(ticker_upper.endswith(suffix) for suffix in ['-W', '-WT', '.W', '.WT', '/W', '_W', '-WS']):
            logger.debug(f"Filtering warrant: {ticker}")
            return True
        
        # Unit patterns: -U, .U, /U, _U
        if any(ticker_upper.endswith(suffix) for suffix in ['-U', '.U', '/U', '_U']):
            logger.debug(f"Filtering unit: {ticker}")
            return True
        
        # When-issued patterns: -WI, .WI, /WI, _WI
        if any(ticker_upper.endswith(suffix) for suffix in ['-WI', '.WI', '/WI', '_WI']):
            logger.debug(f"Filtering when-issued: {ticker}")
            return True
        
        # Simple suffix patterns for warrants/rights/units without separators (5+ char symbols)
        # e.g., AAAAW (warrant), AAAAR (right), AAAAU (unit)
        if len(ticker) >= 5 and ticker_upper[-1] in ['W', 'R', 'U']:
            logger.debug(f"Filtering warrant/right/unit suffix: {ticker}")
            return True
        
        # OTC/foreign stock suffix pattern (5+ char symbols ending in F)
        # e.g., MOBNF, MVVYF, KGSSF - typically Canadian/foreign stocks on OTC markets
        if len(ticker) >= 5 and ticker_upper[-1] == 'F':
            logger.debug(f"Filtering OTC suffix: {ticker}")
            return True
        
        # Test/suspended tickers: starts with Z on some exchanges (but not Asian exchanges)
        if ticker_upper.startswith('Z') and exchange not in self.ASIAN_HOME_EXCHANGES:
            # Only filter if it looks like a test ticker (very short or has numbers)
            if len(ticker) <= 2 or any(c.isdigit() for c in ticker):
                logger.debug(f"Filtering test/suspended ticker: {ticker}")
                return True
        
        # Allow all tickers from Asian home exchanges (including numeric ones)
        if exchange in self.ASIAN_HOME_EXCHANGES:
            return False
        
        # Allow all other tickers (US, Canada, legitimate European companies, etc.)
        return False
    
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
            'us': ['america'],  # US only
            'north_america': ['america', 'canada'],  # US + Canada
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
                             'typespecs',                     # Security type (common, preferred, etf, etc.)
                             'total_revenue',                 # Total Revenue
                             'total_debt',                    # Total Debt
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
                    
                    fetched_count = len(df)
                    filtered_count = 0
                    
                    # Convert DataFrame to dictionary keyed by ticker
                    for _, row in df.iterrows():
                        ticker = row.get('name')
                        exchange = row.get('exchange')
                        typespecs = row.get('typespecs', [])
                        
                        if not ticker:
                            continue
                        
                        # Filter by security type (typespecs) - only include common stocks and REITs
                        # This excludes: etf, preferred, unit, closedend, trust, dr
                        if typespecs:
                            # typespecs is a list like ['common'] or ['preferred']
                            if not any(spec in self.ALLOWED_TYPESPECS for spec in typespecs):
                                filtered_count += 1
                                logger.debug(f"Filtering {ticker}: typespecs={typespecs}")
                                continue
                        
                        # Apply hybrid filtering logic (exchange-based and pattern-based)
                        if self._should_skip_ticker(ticker, exchange):
                            filtered_count += 1
                            continue
                        
                        # Skip duplicates (in case same ticker appears in multiple markets)
                        if ticker not in all_results:
                            all_results[ticker] = self._normalize_row(row)
                    
                    if filtered_count > 0:
                        print(f"  ✓ {market}: {len(df)} stocks ({filtered_count} filtered)")
                    else:
                        print(f"  ✓ {market}: {len(df)} stocks")
                    
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
            'total_revenue': row.get('total_revenue'),
            'total_debt': row.get('total_debt'),
        }
