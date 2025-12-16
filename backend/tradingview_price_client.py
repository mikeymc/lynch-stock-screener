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

logger = logging.getLogger(__name__)


class TradingViewPriceClient:
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
        
        try:
            # Fetch all available historical data
            ticker = yf.Ticker(symbol)
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
            
        except Exception as e:
            logger.error(f"[PriceHistoryFetcher] Error fetching history for {symbol}: {type(e).__name__}: {e}")
            return None
    
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
            logger.warning(f"[PriceHistoryFetcher][{symbol}] No weekly price data available")
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
    
    def is_available(self) -> bool:
        """
        Check if the price client is available.
        
        Returns:
            True (yfinance is always available)
        """
        return self._available


# Global singleton instance
_default_client = None


def get_tradingview_price_client() -> TradingViewPriceClient:
    """Get or create the default TradingView price client instance"""
    global _default_client
    if _default_client is None:
        _default_client = TradingViewPriceClient()
    return _default_client
