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
    
    def fetch_and_cache_all(self, symbol: str):
        """
        Fetch and cache all SEC data (filings + sections) in one call.
        
        Only fetches for US stocks to avoid unnecessary API calls.
        
        Args:
            symbol: Stock ticker symbol
        """
        try:
            # Only fetch for US stocks
            stock_metrics = self.db.get_stock_metrics(symbol)
            if stock_metrics:
                country = stock_metrics.get('country', '').upper()
                if country not in ('US', 'USA', 'UNITED STATES', ''):
                    logger.debug(f"[SECDataFetcher][{symbol}] Skipping SEC data (non-US stock: {country})")
                    return
            
            # Fetch filings list
            logger.debug(f"[SECDataFetcher][{symbol}] Fetching SEC filings")
            filings = self.edgar_fetcher.fetch_recent_filings(symbol)
            
            if filings:
                for filing in filings:
                    self.db.save_sec_filing(
                        symbol,
                        filing['type'],
                        filing['date'],
                        filing['url'],
                        filing['accession_number']
                    )
                logger.info(f"[SECDataFetcher][{symbol}] Cached {len(filings)} SEC filings")
            
            # Fetch 10-K sections
            logger.debug(f"[SECDataFetcher][{symbol}] Fetching 10-K sections")
            sections_10k = self.edgar_fetcher.extract_filing_sections(symbol, '10-K')
            
            if sections_10k:
                for name, data in sections_10k.items():
                    self.db.save_filing_section(
                        symbol, name, data['content'],
                        data['filing_type'], data['filing_date']
                    )
                logger.info(f"[SECDataFetcher][{symbol}] Cached {len(sections_10k)} 10-K sections")
            
            # Fetch 10-Q sections
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
