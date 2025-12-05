# ABOUTME: TradingView price client using tvDatafeed for historical stock prices
# ABOUTME: Provides the same interface as SchwabClient for seamless migration

"""
TradingView Price Client

Uses the tvDatafeed library to fetch historical stock prices from TradingView.
This is a drop-in replacement for SchwabClient with the same interface.

Key features:
- No authentication required for basic use
- Up to 5000 bars of historical data per request
- Supports daily, weekly, and intraday intervals
"""

import logging
from typing import Optional
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class TradingViewPriceClient:
    """Client for fetching historical stock prices from TradingView via tvDatafeed"""
    
    # Map common exchange names to TradingView exchange codes
    EXCHANGE_MAP = {
        'NASDAQ': 'NASDAQ',
        'NYSE': 'NYSE',
        'AMEX': 'AMEX',
        'ARCA': 'AMEX',  # NYSE Arca ETFs
        'BATS': 'BATS',
        'OTC': 'OTC',
    }
    
    def __init__(self, username: str = None, password: str = None):
        """
        Initialize TradingView price client.
        
        Args:
            username: Optional TradingView username for extended access
            password: Optional TradingView password
        """
        self.username = username
        self.password = password
        self._tv = None
        self._initialized = False
        self._available = True
        
        # Cache for recently fetched data to avoid redundant API calls
        self._price_cache = {}
        self._cache_ttl_hours = 24
    
    def _get_client(self):
        """Lazy initialization of tvDatafeed client"""
        if self._tv is None:
            try:
                from tvDatafeed import TvDatafeed
                
                if self.username and self.password:
                    self._tv = TvDatafeed(self.username, self.password)
                else:
                    # Use without login - some symbols may be limited
                    self._tv = TvDatafeed()
                
                self._initialized = True
                logger.info("TradingView price client initialized successfully")
            except ImportError:
                logger.error("tvDatafeed library not installed. Run: pip install --upgrade --no-cache-dir git+https://github.com/rongardF/tvdatafeed.git")
                self._available = False
                return None
            except Exception as e:
                logger.error(f"Failed to initialize TradingView client: {type(e).__name__}: {e}")
                self._available = False
                return None
        
        return self._tv
    
    def _find_exchange(self, symbol: str) -> str:
        """
        Determine the exchange for a given symbol.
        
        Most US stocks are on NASDAQ or NYSE. We try NASDAQ first,
        then fall back to NYSE.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Exchange code string
        """
        # For now, try NASDAQ first as it covers most tech stocks
        # If we get errors, we could implement smarter detection
        return 'NASDAQ'
    
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
            logger.error(f"Invalid date format: {target_date}. Expected YYYY-MM-DD")
            return None
        
        # Don't fetch future dates
        if date_obj > datetime.now():
            logger.warning(f"Cannot fetch price for future date: {target_date}")
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
            
            # Get dates on or before target
            valid_dates = df.index[df.index <= target_ts]
            
            if len(valid_dates) == 0:
                # Target date is before all available data
                logger.warning(f"No data available for {symbol} on or before {target_date}")
                return None
            
            # Get the closest date (most recent on or before target)
            closest_date = valid_dates.max()
            price = float(df.loc[closest_date, 'close'])
            
            # Cache the individual price result
            self._price_cache[cache_key] = {
                'price': price,
                'timestamp': datetime.now()
            }
            
            logger.info(f"Fetched price for {symbol} on {target_date}: ${price:.2f} (actual date: {closest_date.date()})")
            return price
            
        except Exception as e:
            logger.error(f"Error looking up price for {symbol} on {target_date}: {type(e).__name__}: {e}")
            return None
    
    def _get_symbol_history(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Get full price history for a symbol, using cache to avoid repeated API calls.
        
        This fetches 5000 bars (~20 years) of daily data once and caches it,
        so multiple date lookups only need one API call.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            DataFrame with price history, or None if unavailable
        """
        import time
        
        # Check symbol-level cache
        cache_key = f"_history_{symbol}"
        if cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            if datetime.now() - cached['timestamp'] < timedelta(hours=self._cache_ttl_hours):
                return cached['data']
        
        # Get tvDatafeed client
        tv = self._get_client()
        if tv is None:
            return None
        
        try:
            from tvDatafeed import Interval
            
            # Fetch maximum daily data (5000 bars ≈ 20 years)
            n_bars = 5000
            
            # Try different exchanges since stocks can be on different ones
            exchanges = ['NASDAQ', 'NYSE', 'AMEX', 'BATS']
            
            df = None
            for exchange in exchanges:
                # Retry logic with delay to handle connection issues
                for attempt in range(3):
                    try:
                        df = tv.get_hist(
                            symbol=symbol.upper(),
                            exchange=exchange,
                            interval=Interval.in_daily,
                            n_bars=n_bars
                        )
                        if df is not None and not df.empty:
                            logger.debug(f"Found {symbol} on {exchange} with {len(df)} bars")
                            break
                    except Exception as e:
                        if attempt < 2:
                            logger.debug(f"Attempt {attempt + 1} failed for {symbol} on {exchange}, retrying...")
                            time.sleep(1)  # Wait before retry
                        else:
                            logger.debug(f"{symbol} not found on {exchange}: {e}")
                
                if df is not None and not df.empty:
                    break
                    
                # Small delay between exchanges to avoid rate limiting
                time.sleep(0.5)
            
            if df is None or df.empty:
                logger.warning(f"No price data found for {symbol}")
                return None
            
            # Ensure datetime index
            df.index = pd.to_datetime(df.index)
            
            # Cache the full history
            self._price_cache[cache_key] = {
                'data': df,
                'timestamp': datetime.now()
            }
            
            logger.info(f"Cached {len(df)} bars of price history for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}: {type(e).__name__}: {e}")
            return None
    
    def is_available(self) -> bool:
        """
        Check if the TradingView price client is available.
        
        Returns:
            True if client can make requests, False otherwise
        """
        if not self._available:
            return False
        
        # Try to initialize if not done yet
        if not self._initialized:
            return self._get_client() is not None
        
        return True
    
    def get_weekly_price_history(self, symbol: str, start_year: int = None) -> dict:
        """
        Get weekly price history for a symbol.
        
        Uses cached daily data and resamples to weekly (Friday close).
        
        Args:
            symbol: Stock ticker symbol
            start_year: Optional start year filter (e.g., 2013)
            
        Returns:
            Dict with 'dates' and 'prices' arrays, or empty dict if unavailable
        """
        df = self._get_symbol_history(symbol)
        if df is None or df.empty:
            return {'dates': [], 'prices': []}
        
        try:
            # Filter by start year if specified
            if start_year:
                start_date = f"{start_year}-01-01"
                df = df[df.index >= start_date]
            
            # Resample to weekly (Friday close)
            weekly = df['close'].resample('W-FRI').last()
            
            # Drop any NaN values
            weekly = weekly.dropna()
            
            # Convert to lists
            dates = [d.strftime('%Y-%m-%d') for d in weekly.index]
            prices = [float(p) for p in weekly.values]
            
            logger.info(f"Generated {len(dates)} weekly prices for {symbol}" + 
                       (f" from {start_year}" if start_year else ""))
            
            return {
                'dates': dates,
                'prices': prices
            }
            
        except Exception as e:
            logger.error(f"Error generating weekly prices for {symbol}: {type(e).__name__}: {e}")
            return {'dates': [], 'prices': []}
    
    def clear_cache(self):
        """Clear the price cache"""
        self._price_cache.clear()
        logger.info("Price cache cleared")


# Singleton instance for use across the app
_default_client = None


def get_tradingview_price_client() -> TradingViewPriceClient:
    """Get the default TradingView price client instance"""
    global _default_client
    if _default_client is None:
        _default_client = TradingViewPriceClient()
    return _default_client
