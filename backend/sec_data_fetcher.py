# ABOUTME: Fetches and caches SEC filing data (filings list and sections)
# ABOUTME: Handles both 10-K and 10-Q filings for US stocks only

import logging
from typing import Optional, Dict, Any
from database import Database
from edgar_fetcher import EdgarFetcher

logger = logging.getLogger(__name__)


class SECDataFetcher:
    """Fetches and caches SEC filing data for stocks"""
    
    def __init__(self, db: Database, edgar_fetcher: EdgarFetcher):
        self.db = db
        self.edgar_fetcher = edgar_fetcher
    
    def fetch_and_cache_all(self, symbol: str, force_refresh: bool = False):
        """
        Fetch and cache all SEC data (filings + sections) in one call.
        
        Only fetches for US stocks to avoid unnecessary API calls.
        Uses smart incremental fetching:
        - Checks for new filings since the last cached filing date
        - Only downloads content for new filings
        - Skips entirely if no new filings available
        
        Args:
            symbol: Stock ticker symbol
            force_refresh: If True, bypass cache and fetch all data
        """
        try:
            # Only fetch for US stocks
            stock_metrics = self.db.get_stock_metrics(symbol)
            if stock_metrics:
                country = stock_metrics.get('country', '').upper()
                if country not in ('US', 'USA', 'UNITED STATES', ''):
                    logger.debug(f"[SECDataFetcher][{symbol}] Skipping SEC data (non-US stock: {country})")
                    return
            
            # Get the latest cached filing date for incremental fetch
            since_date = None
            if not force_refresh:
                since_date = self.db.get_latest_sec_filing_date(symbol)
                if since_date:
                    logger.debug(f"[SECDataFetcher][{symbol}] Incremental fetch: looking for filings after {since_date}")
            
            # Fetch filings list (will only return new filings if since_date is set)
            logger.debug(f"[SECDataFetcher][{symbol}] Fetching SEC filings")
            filings = self.edgar_fetcher.fetch_recent_filings(symbol, since_date=since_date)
            
            if not filings:
                if since_date:
                    logger.debug(f"[SECDataFetcher][{symbol}] No new 10-K/10-Q filings since {since_date}")
                else:
                    logger.debug(f"[SECDataFetcher][{symbol}] No 10-K/10-Q filings available")
                return
            
            # Save new filings
            for filing in filings:
                self.db.save_sec_filing(
                    symbol,
                    filing['type'],
                    filing['date'],
                    filing['url'],
                    filing['accession_number']
                )
            logger.info(f"[SECDataFetcher][{symbol}] Cached {len(filings)} {'new ' if since_date else ''}SEC filings")
            
            # Check if we have new 10-K filings - extract sections if so
            has_new_10k = any(f['type'] == '10-K' for f in filings)
            has_new_10q = any(f['type'] == '10-Q' for f in filings)
            
            # Fetch 10-K sections if we have a new 10-K
            if has_new_10k or force_refresh:
                logger.debug(f"[SECDataFetcher][{symbol}] Fetching 10-K sections")
                sections_10k = self.edgar_fetcher.extract_filing_sections(symbol, '10-K')
                
                if sections_10k:
                    for name, data in sections_10k.items():
                        self.db.save_filing_section(
                            symbol, name, data['content'],
                            data['filing_type'], data['filing_date']
                        )
                    logger.info(f"[SECDataFetcher][{symbol}] Cached {len(sections_10k)} 10-K sections")
            
            # Fetch 10-Q sections if we have a new 10-Q
            if has_new_10q or force_refresh:
                logger.debug(f"[SECDataFetcher][{symbol}] Fetching 10-Q sections")
                sections_10q = self.edgar_fetcher.extract_filing_sections(symbol, '10-Q')
                
                if sections_10q:
                    for name, data in sections_10q.items():
                        self.db.save_filing_section(
                            symbol, name, data['content'],
                            data['filing_type'], data['filing_date']
                        )
                    logger.info(f"[SECDataFetcher][{symbol}] Cached {len(sections_10q)} 10-Q sections")
        
        except Exception as e:
            logger.error(f"[SECDataFetcher][{symbol}] Error caching SEC data: {e}")
            # Don't raise - SEC data is optional

