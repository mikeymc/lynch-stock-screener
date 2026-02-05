# ABOUTME: Fetches and caches SEC filing data (filings list and sections)
# ABOUTME: Handles 10-K, 10-Q, 20-F (FPI annual), and 6-K (FPI interim) filings

import logging
import time
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
        t_start = time.time()
        
        try:
            # Stage 1: Check if company files with SEC (has CIK)
            # This allows Foreign Private Issuers (20-F filers) to be processed
            t0 = time.time()
            cik = self.edgar_fetcher.get_cik_for_ticker(symbol)
            t_cik = (time.time() - t0) * 1000
            
            if not cik:
                logger.debug(f"[SECDataFetcher][{symbol}] Skipping SEC data (no CIK found)")
                return
            
            # Stage 2: Get the latest cached filing date for incremental fetch
            t0 = time.time()
            since_date = None
            if not force_refresh:
                since_date = self.db.get_latest_sec_filing_date(symbol)
                if since_date:
                    logger.debug(f"[SECDataFetcher][{symbol}] Incremental fetch: looking for filings after {since_date}")
            t_since = (time.time() - t0) * 1000
            
            # Stage 3: Fetch filings list (will only return new filings if since_date is set)
            t0 = time.time()
            filings = self.edgar_fetcher.fetch_recent_filings(symbol, since_date=since_date)
            t_filings = (time.time() - t0) * 1000
            
            if not filings:
                if since_date:
                    logger.debug(f"[SECDataFetcher][{symbol}] No new SEC filings since {since_date}")
                else:
                    logger.debug(f"[SECDataFetcher][{symbol}] No SEC filings available")
                # Log timing even for early return
                logger.info(f"[{symbol}] timing: cik={t_cik:.0f}ms since_date={t_since:.0f}ms filings={t_filings:.0f}ms (no new filings)")
                return
            
            # Stage 4: Save new filings
            t0 = time.time()
            for filing in filings:
                self.db.save_sec_filing(
                    symbol,
                    filing['type'],
                    filing['date'],
                    filing['url'],
                    filing['accession_number']
                )
            t_save_filings = (time.time() - t0) * 1000
            logger.info(f"[SECDataFetcher][{symbol}] Cached {len(filings)} {'new ' if since_date else ''}SEC filings")
            
            # Check if we have new annual filings (10-K for US, 20-F for FPI) - extract sections if so
            has_new_10k = any(f['type'] == '10-K' for f in filings)
            has_new_20f = any(f['type'] == '20-F' for f in filings)
            has_new_10q = any(f['type'] in ['10-Q', '6-K'] for f in filings)
            
            t_10k = 0
            t_20f = 0
            t_10q = 0
            
            # Stage 5: Fetch 10-K sections if we have a new 10-K
            if has_new_10k or force_refresh:
                t0 = time.time()
                sections_10k = self.edgar_fetcher.extract_filing_sections(symbol, '10-K')
                t_10k = (time.time() - t0) * 1000
                
                if sections_10k:
                    for name, data in sections_10k.items():
                        self.db.save_filing_section(
                            symbol, name, data['content'],
                            data['filing_type'], data['filing_date']
                        )
                    logger.info(f"[SECDataFetcher][{symbol}] Cached {len(sections_10k)} 10-K sections")
            
            # Stage 5b: Fetch 20-F sections if we have a new 20-F (Foreign Private Issuer annual report)
            if has_new_20f or force_refresh:
                t0 = time.time()
                sections_20f = self.edgar_fetcher.extract_filing_sections(symbol, '20-F')
                t_20f = (time.time() - t0) * 1000
                
                if sections_20f:
                    for name, data in sections_20f.items():
                        self.db.save_filing_section(
                            symbol, name, data['content'],
                            data['filing_type'], data['filing_date']
                        )
                    logger.info(f"[SECDataFetcher][{symbol}] Cached {len(sections_20f)} 20-F sections")
            
            # Stage 6: Fetch 10-Q sections if we have a new 10-Q
            if has_new_10q or force_refresh:
                t0 = time.time()
                sections_10q = self.edgar_fetcher.extract_filing_sections(symbol, '10-Q')
                t_10q = (time.time() - t0) * 1000
                
                if sections_10q:
                    for name, data in sections_10q.items():
                        self.db.save_filing_section(
                            symbol, name, data['content'],
                            data['filing_type'], data['filing_date']
                        )
                    logger.info(f"[SECDataFetcher][{symbol}] Cached {len(sections_10q)} 10-Q sections")
            
            # Final timing summary
            t_total = (time.time() - t_start) * 1000
            logger.info(f"[{symbol}] timing: cik={t_cik:.0f}ms since={t_since:.0f}ms filings={t_filings:.0f}ms save={t_save_filings:.0f}ms 10K={t_10k:.0f}ms 20F={t_20f:.0f}ms 10Q={t_10q:.0f}ms TOTAL={t_total:.0f}ms")
        
        except Exception as e:
            logger.error(f"[SECDataFetcher][{symbol}] Error caching SEC data: {e}")
            # Don't raise - SEC data is optional

