# ABOUTME: Price client using yfinance for historical stock prices
# ABOUTME: Provides unlimited historical data with no rate limits

"""
YFinance Price Client

Uses yfinance to fetch historical stock prices from Yahoo Finance.
Replaces tvDatafeed with a faster, unlimited alternative.

Key features:
- No rate limits
- Unlimited historical data (decades back)
- Fast and reliable
- Same interface as before for seamless migration
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
import yfinance.cache as yf_cache
from yfinance_rate_limiter import with_timeout_and_retry

logger = logging.getLogger(__name__)

# Suppress yfinance's noisy logging (e.g., "possibly delisted" for recent date queries)
# Must use CRITICAL because ERROR is higher priority than WARNING
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# Disable yfinance's internal SQLite caches to prevent "database is locked" errors
# under concurrent thread access. We monkey-patch the cache managers to use
# Dummy (no-op) implementations instead of SQLite-backed ones.
def _init_dummy_tz_cache(self, cache_dir=None):
    self._cache = yf_cache._TzCacheDummy()

def _init_dummy_cookie_cache(self, cache_dir=None):
    self._cache = yf_cache._CookieCacheDummy()

yf_cache._TzCacheManager.initialise = _init_dummy_tz_cache
yf_cache._CookieCacheManager.initialise = _init_dummy_cookie_cache


class YFinancePriceClient:
    """Client for fetching historical stock prices using yfinance"""
    
    def __init__(self, username: str = None, password: str = None):
        """
        Initialize price client.
        
        Args:
            username: Unused (kept for API compatibility)
            password: Unused (kept for API compatibility)
        """
        self._price_cache = {}
        self._cache_ttl_hours = 24
        self._available = True
    
    def _normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol for Yahoo Finance compatibility.
        
        Yahoo Finance uses hyphens for share classes (BRK-B), 
        but TradingView uses dots (BRK.B).
        """
        # Convert dots to hyphens for share class notation
        return symbol.replace('.', '-')
    
    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance price history")
    def _get_symbol_history(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Fetch full price history for a symbol using yfinance.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            DataFrame with OHLCV data, or None if unavailable
        """
        # Check symbol-level cache
        cache_key = f"_history_{symbol}"
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            if datetime.now() - cached['timestamp'] < timedelta(hours=self._cache_ttl_hours):
                return cached['data']
        
        # Normalize symbol for Yahoo Finance (e.g., BRK.B -> BRK-B)
        yf_symbol = self._normalize_symbol(symbol)
        
        # Fetch all available historical data
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="max", auto_adjust=False)
        
        if df is None or df.empty:
            logger.warning(f"[PriceHistoryFetcher] No price data found for {symbol}")
            return None
        
        # Ensure datetime index
        df.index = pd.to_datetime(df.index)
        
        # Rename columns to match expected format (lowercase)
        df.columns = df.columns.str.lower()
        
        # Cache the full history
        self._price_cache[cache_key] = {
            'data': df,
            'timestamp': datetime.now()
        }
        
        logger.info(f"[PriceHistoryFetcher] Cached {len(df)} bars of price history for {symbol}")
        return df
    
    def get_historical_price(self, symbol: str, target_date: str) -> Optional[float]:
        """
        Fetch the closing price for a stock on or near a specific date.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
            target_date: Date in YYYY-MM-DD format
            
        Returns:
            Closing price as float, or None if unavailable
        """
        # Validate date format
        try:
            date_obj = datetime.strptime(target_date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"[PriceHistoryFetcher] Invalid date format: {target_date}. Expected YYYY-MM-DD")
            return None
        
        # Don't fetch future dates
        if date_obj > datetime.now():
            logger.warning(f"[PriceHistoryFetcher] Cannot fetch price for future date: {target_date}")
            return None
        
        # Check individual price cache first
        cache_key = f"{symbol}_{target_date}"
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            if datetime.now() - cached['timestamp'] < timedelta(hours=self._cache_ttl_hours):
                return cached['price']
        
        # Get the full price history for this symbol (cached)
        df = self._get_symbol_history(symbol)
        if df is None or df.empty:
            return None
        
        try:
            # Find the closest date to target_date
            target_ts = pd.Timestamp(date_obj)
            
            # Ensure target_ts has matching timezone if df.index is timezone-aware
            if df.index.tz is not None:
                # Localize to match df.index timezone
                target_ts = target_ts.tz_localize(df.index.tz)
            
            # Get dates on or before target
            valid_dates = df.index[df.index <= target_ts]
            
            if len(valid_dates) == 0:
                # Target date is before all available data
                logger.warning(f"[PriceHistoryFetcher] No data available for {symbol} on or before {target_date}")
                return None
            
            # Get the closest date (most recent on or before target)
            closest_date = valid_dates.max()
            price = float(df.loc[closest_date, 'close'])
            
            # Cache the individual price result
            self._price_cache[cache_key] = {
                'price': price,
                'timestamp': datetime.now()
            }
            
            logger.info(f"[PriceHistoryFetcher] Fetched cached price for {symbol} on {target_date}: ${price:.2f} (actual date: {closest_date.date()})")
            return price
            
        except Exception as e:
            logger.error(f"[PriceHistoryFetcher] Error looking up price for {symbol} on {target_date}: {type(e).__name__}: {e}")
            return None
    
    def get_weekly_price_history(self, symbol: str, start_year: int = None) -> Optional[Dict[str, Any]]:
        """
        Get weekly price history for a symbol.
        
        Args:
            symbol: Stock ticker symbol
            start_year: Optional start year (default: all available data)
            
        Returns:
            Dict with 'dates' and 'prices' lists, or None if unavailable
        """
        # Get full daily history
        df = self._get_symbol_history(symbol)
        if df is None or df.empty:
            logger.debug(f"[PriceHistoryFetcher][{symbol}] No weekly price data available")
            return None
        
        try:
            # Resample to weekly (Friday close)
            weekly_df = df['close'].resample('W-FRI').last().dropna()
            
            # Filter by start year if specified
            if start_year:
                weekly_df = weekly_df[weekly_df.index.year >= start_year]
            
            if weekly_df.empty:
                logger.warning(f"[PriceHistoryFetcher][{symbol}] No weekly data after filtering")
                return None
            
            # Convert to lists
            dates = [d.strftime('%Y-%m-%d') for d in weekly_df.index]
            prices = weekly_df.tolist()
            
            logger.info(f"[PriceHistoryFetcher] Generated {len(dates)} weekly prices for {symbol}")
            
            return {
                'dates': dates,
                'prices': prices
            }
            
        except Exception as e:
            logger.error(f"[PriceHistoryFetcher] Error generating weekly prices for {symbol}: {e}")
            return None
    
    def get_weekly_price_history_since(self, symbol: str, start_date: str) -> Optional[Dict[str, Any]]:
        """
        Get weekly price history for a symbol starting from a specific date.
        
        This is optimized for incremental updates - fetches only new data after
        the most recent cached date, which is ~4x faster than fetching full history.
        
        Args:
            symbol: Stock ticker symbol
            start_date: Start date in 'YYYY-MM-DD' format
            
        Returns:
            Dict with 'dates' and 'prices' lists for weeks after start_date, or None if unavailable
        """
        try:
            # Normalize symbol for Yahoo Finance (e.g., BRK.B -> BRK-B)
            yf_symbol = self._normalize_symbol(symbol)
            
            # Fetch data starting from the given date
            # Note: yfinance includes the start date, so we'll get one overlapping week
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(start=start_date, interval='1wk')
            
            # Check if start_date is recent (within last 7 days)
            # If so, empty data means "already up to date", not failure
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                is_recent = (datetime.now() - start_dt).days <= 7
            except ValueError:
                is_recent = False
            
            if df is None or df.empty:
                if is_recent:
                    # Recent start date with no data = already current, not a failure
                    logger.debug(f"[YFinancePriceClient][{symbol}] Already up to date (no new data since {start_date})")
                    return {'dates': [], 'prices': []}
                else:
                    logger.warning(f"[YFinancePriceClient][{symbol}] No price data available since {start_date}")
                    return None
            
            # Extract close prices
            if 'Close' in df.columns:
                weekly_df = df['Close'].dropna()
            elif 'close' in df.columns:
                weekly_df = df['close'].dropna()
            else:
                logger.error(f"[YFinancePriceClient][{symbol}] No 'Close' column in data")
                return None
            
            if weekly_df.empty:
                if is_recent:
                    logger.debug(f"[YFinancePriceClient][{symbol}] Already up to date (no new data since {start_date})")
                    return {'dates': [], 'prices': []}
                else:
                    logger.warning(f"[YFinancePriceClient][{symbol}] No weekly data after filtering")
                    return None
            
            # Skip the first row to avoid duplicate (it's the start_date we already have)
            if len(weekly_df) > 1:
                weekly_df = weekly_df.iloc[1:]
            else:
                # No new data
                logger.debug(f"[YFinancePriceClient][{symbol}] No new data since {start_date}")
                return {'dates': [], 'prices': []}
            
            # Convert to lists
            dates = [d.strftime('%Y-%m-%d') for d in weekly_df.index]
            prices = weekly_df.tolist()
            
            logger.info(f"[YFinancePriceClient] Fetched {len(dates)} new weekly prices for {symbol} since {start_date}")
            
            return {
                'dates': dates,
                'prices': prices
            }
            
        except Exception as e:
            logger.error(f"[YFinancePriceClient] Error fetching weekly prices for {symbol} since {start_date}: {e}")
            return None
    
    def is_available(self) -> bool:
        """
        Check if the price client is available.
        
        Returns:
            True (yfinance is always available)
        """
        return self._available


# Global singleton instance
_default_client = None


def get_yfinance_price_client() -> YFinancePriceClient:
    """Get or create the default yfinance price client instance"""
    global _default_client
    if _default_client is None:
        _default_client = YFinancePriceClient()
    return _default_client
