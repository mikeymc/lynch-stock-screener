# ABOUTME: Fetches and caches price history data for stocks
# ABOUTME: Handles both daily price history and weekly price aggregation

import logging
from typing import Optional, Dict, Any
from database import Database
from tradingview_price_client import TradingViewPriceClient

logger = logging.getLogger(__name__)


class PriceHistoryFetcher:
    """Fetches and caches historical price data for stocks"""
    
    def __init__(self, db: Database, price_client: TradingViewPriceClient):
        self.db = db
        self.price_client = price_client
    
    def fetch_and_cache_prices(self, symbol: str):
        """
        Fetch and cache all price history for a symbol.
        
        This includes:
        1. Weekly price history for charts
        2. Fiscal year-end prices for P/E ratio calculation
        
        Args:
            symbol: Stock ticker symbol
        """
        try:
            # 1. Get weekly prices from tvdatafeed
            logger.debug(f"[PriceHistoryFetcher][{symbol}] Fetching weekly price history")
            weekly_data = self.price_client.get_weekly_price_history(symbol)
            
            if weekly_data and weekly_data.get('dates') and weekly_data.get('prices'):
                # Save to database
                self.db.save_weekly_prices(symbol, weekly_data)
                logger.info(f"[PriceHistoryFetcher][{symbol}] Cached {len(weekly_data['dates'])} weekly prices")
            else:
                logger.warning(f"[PriceHistoryFetcher][{symbol}] No weekly price data available")
            
            # 2. Get fiscal year-end dates from earnings history
            earnings = self.db.get_earnings_history(symbol, period_type='annual')
            
            if not earnings:
                logger.debug(f"[PriceHistoryFetcher][{symbol}] No earnings history, skipping fiscal year-end prices")
                return
            
            # 3. Fetch and cache price for each fiscal year end
            prices_cached = 0
            for entry in earnings:
                fiscal_end = entry.get('fiscal_end')
                if not fiscal_end:
                    continue
                
                try:
                    price = self.price_client.get_historical_price(symbol, fiscal_end)
                    if price:
                        # Save individual price point
                        self.db.save_price_point(symbol, fiscal_end, price)
                        prices_cached += 1
                except Exception as e:
                    logger.debug(f"[PriceHistoryFetcher][{symbol}] Failed to fetch price for {fiscal_end}: {e}")
            
            if prices_cached > 0:
                logger.info(f"[PriceHistoryFetcher][{symbol}] Cached {prices_cached} fiscal year-end prices")
        
        except Exception as e:
            logger.error(f"[PriceHistoryFetcher][{symbol}] Error caching price history: {e}")
            raise
