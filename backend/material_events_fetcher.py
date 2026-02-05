# ABOUTME: Fetches and caches material events (8-K filings) from SEC
# ABOUTME: Handles 8-K filing parsing and database storage

import logging
from datetime import datetime, timedelta
from typing import Optional
from database import Database
from sec_8k_client import SEC8KClient

logger = logging.getLogger(__name__)


class MaterialEventsFetcher:
    """Fetches and caches material events (8-K filings) for stocks"""
    
    def __init__(self, db: Database, sec_8k_client: SEC8KClient, data_fetcher=None):
        self.db = db
        self.sec_8k_client = sec_8k_client
        self.data_fetcher = data_fetcher
    
    def fetch_and_cache_events(self, symbol: str, force_refresh: bool = False):
        """
        Fetch and cache material events (8-Ks) for a symbol.
        
        Uses smart incremental fetching:
        - Always checks for new filings (lightweight metadata check)
        - Only downloads content for filings we don't already have
        - Catches new 8-K filings immediately while avoiding redundant downloads
        
        Args:
            symbol: Stock ticker symbol
            force_refresh: If True, fetch all filings regardless of cache
        """
        try:
            # Get the latest cached filing date for incremental fetch
            since_date = None
            if not force_refresh:
                since_date = self.db.get_latest_material_event_date(symbol)
                if since_date:
                    logger.debug(f"[MaterialEventsFetcher][{symbol}] Incremental fetch: looking for filings after {since_date}")
            
            # Fetch filings (will skip content download for already-cached filings)
            events = self.sec_8k_client.fetch_recent_8ks(symbol, since_date=since_date)
            
            if not events:
                if since_date:
                    logger.debug(f"[MaterialEventsFetcher][{symbol}] No new 8-K filings since {since_date}")
                else:
                    logger.debug(f"[MaterialEventsFetcher][{symbol}] No 8-K filings available")
                return
            
            # Save new events
            for event in events:
                self.db.save_material_event(symbol, event)
                
                # Process Earnings (Item 2.02) if data_fetcher is available
                if self.data_fetcher and '2.02' in event.get('sec_item_codes', []):
                    self.data_fetcher.process_item_202(symbol, event)
            
            logger.info(f"[MaterialEventsFetcher][{symbol}] Cached {len(events)} {'new ' if since_date else ''}material events")
        
        except Exception as e:
            logger.error(f"[MaterialEventsFetcher][{symbol}] Error caching material events: {e}")
            # Don't raise - material events are optional
