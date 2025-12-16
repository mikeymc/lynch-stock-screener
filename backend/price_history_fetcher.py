# ABOUTME: Fetches and caches price history data for stocks
# ABOUTME: Handles both daily price history and weekly price aggregation

import logging
from typing import Optional, Dict, Any
from threading import Semaphore
from database import Database
from yfinance_price_client import YFinancePriceClient

logger = logging.getLogger(__name__)


class PriceHistoryFetcher:
    """Fetches and caches historical price data for stocks"""
    
    def __init__(self, db: Database, price_client: YFinancePriceClient, yf_semaphore: Semaphore = None):
        self.db = db
        self.price_client = price_client
        self.yf_semaphore = yf_semaphore
    
    def fetch_and_cache_prices(self, symbol: str):
        """
        Fetch and cache weekly price history for a symbol.
        
        Note: Fiscal year-end prices are no longer fetched individually since
        we cache the full price history - year-end prices can be queried
        from the weekly cache as needed.
        
        Args:
            symbol: Stock ticker symbol
        """
        # Acquire semaphore to limit concurrent yfinance requests
        if self.yf_semaphore:
            self.yf_semaphore.acquire()
        
        try:
            # Get weekly prices from yfinance
            logger.debug(f"[PriceHistoryFetcher][{symbol}] Fetching weekly price history")
            weekly_data = self.price_client.get_weekly_price_history(symbol)
            
            if weekly_data and weekly_data.get('dates') and weekly_data.get('prices'):
                # Save to database
                self.db.save_weekly_prices(symbol, weekly_data)
                logger.info(f"[PriceHistoryFetcher][{symbol}] Cached {len(weekly_data['dates'])} weekly prices")
            else:
                logger.warning(f"[PriceHistoryFetcher][{symbol}] No weekly price data available")
        
        except Exception as e:
            logger.error(f"[PriceHistoryFetcher][{symbol}] Error caching price history: {e}")
            raise
        finally:
            # Always release semaphore, even if error occurred
            if self.yf_semaphore:
                self.yf_semaphore.release()
