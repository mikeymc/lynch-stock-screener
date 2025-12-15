# ABOUTME: Fetches and caches material events (8-K filings) from SEC
# ABOUTME: Handles 8-K filing parsing and database storage

import logging
from typing import Optional
from database import Database
from sec_8k_client import SEC8KClient

logger = logging.getLogger(__name__)


class MaterialEventsFetcher:
    """Fetches and caches material events (8-K filings) for stocks"""
    
    def __init__(self, db: Database, sec_8k_client: SEC8KClient):
        self.db = db
        self.sec_8k_client = sec_8k_client
    
    def fetch_and_cache_events(self, symbol: str):
        """
        Fetch and cache material events (8-Ks) for a symbol.
        
        Args:
            symbol: Stock ticker symbol
        """
        try:
            logger.debug(f"[MaterialEventsFetcher][{symbol}] Fetching material events")
            events = self.sec_8k_client.fetch_recent_8ks(symbol)
            
            if not events:
                logger.debug(f"[MaterialEventsFetcher][{symbol}] No material events available")
                return
            
            # Save events
            for event in events:
                self.db.save_material_event(symbol, event)
            
            logger.info(f"[MaterialEventsFetcher][{symbol}] Cached {len(events)} material events")
        
        except Exception as e:
            logger.error(f"[MaterialEventsFetcher][{symbol}] Error caching material events: {e}")
            # Don't raise - material events are optional
