# ABOUTME: Fetches SEC RSS feeds to identify which companies have new filings
# ABOUTME: Used to optimize cache jobs by only processing symbols with new filings

import requests
import logging
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class SECFiling:
    """Represents a filing from the SEC RSS feed"""
    cik: str
    company_name: str
    form_type: str
    filing_date: str
    accession_number: str
    url: str


class SECRSSClient:
    """
    Client for fetching SEC EDGAR RSS feeds.
    
    Uses RSS feeds to efficiently identify which companies have filed new documents,
    avoiding the need to poll the SEC API for every stock in the universe.
    
    Feed types:
    - 8-K: Material events (acquisitions, earnings, leadership changes, etc.)
    - 10-K: Annual reports
    - 10-Q: Quarterly reports
    - 4: Form 4 insider trading disclosures
    """
    
    # SEC RSS feed base URL
    RSS_BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
    
    # Form type mappings for RSS filtering
    FORM_TYPES = {
        '8-K': '8-K',
        '10-K': '10-K',
        '10-Q': '10-Q',
        'FORM4': '4',  # Insider trading
    }
    
    def __init__(self, user_agent: str):
        """
        Initialize SEC RSS client.
        
        Args:
            user_agent: SEC-compliant User-Agent (e.g., "CompanyName email@example.com")
        """
        self.user_agent = user_agent
        self.headers = {
            'User-Agent': user_agent,
            'Accept': 'application/atom+xml, application/xml, text/xml',
            'Accept-Encoding': 'gzip, deflate',
        }
        # Cache for CIK-to-ticker mapping (loaded lazily)
        self._cik_to_ticker: Optional[Dict[str, str]] = None
    
    def _load_cik_to_ticker_mapping(self) -> Dict[str, str]:
        """
        Load SEC's CIK-to-ticker mapping (reverse of ticker-to-CIK).
        
        Returns:
            Dict mapping CIK (10-digit zero-padded) to ticker symbol
        """
        if self._cik_to_ticker is not None:
            return self._cik_to_ticker
        
        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Build reverse mapping: CIK -> ticker
            mapping = {}
            for entry in data.values():
                ticker = entry.get('ticker', '').upper()
                cik = str(entry.get('cik_str', '')).zfill(10)
                if ticker and cik:
                    mapping[cik] = ticker
            
            self._cik_to_ticker = mapping
            logger.info(f"[SECRSSClient] Loaded CIK-to-ticker mapping for {len(mapping)} companies")
            return mapping
            
        except Exception as e:
            logger.error(f"[SECRSSClient] Error loading CIK mapping: {e}")
            self._cik_to_ticker = {}
            return {}
    
    def fetch_recent_filings(
        self, 
        form_type: str, 
        count: int = 100,
        since_date: Optional[str] = None
    ) -> List[SECFiling]:
        """
        Fetch recent filings of a specific type from SEC RSS feed.
        
        Args:
            form_type: Filing type (8-K, 10-K, 10-Q, FORM4)
            count: Number of filings to fetch (max 100 per SEC limit)
            since_date: Optional YYYY-MM-DD date to filter filings after
            
        Returns:
            List of SECFiling objects
        """
        sec_form_type = self.FORM_TYPES.get(form_type.upper(), form_type)
        
        # Build RSS URL
        params = {
            'action': 'getcurrent',
            'type': sec_form_type,
            'count': min(count, 100),  # SEC limits to 100
            'output': 'atom'
        }
        
        try:
            response = requests.get(
                self.RSS_BASE_URL,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            # Parse Atom feed
            filings = self._parse_atom_feed(response.text)
            
            # Filter by date if specified
            if since_date:
                filings = [f for f in filings if f.filing_date >= since_date]
            
            logger.info(f"[SECRSSClient] Fetched {len(filings)} {form_type} filings from RSS feed")
            return filings
            
        except Exception as e:
            logger.error(f"[SECRSSClient] Error fetching RSS feed for {form_type}: {e}")
            return []
    
    def _parse_atom_feed(self, xml_content: str) -> List[SECFiling]:
        """
        Parse Atom XML feed from SEC.
        
        Args:
            xml_content: Raw XML string
            
        Returns:
            List of SECFiling objects
        """
        filings = []
        
        try:
            # Parse XML
            root = ET.fromstring(xml_content)
            
            # Atom namespace
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            # Find all entry elements
            for entry in root.findall('atom:entry', ns):
                try:
                    # Extract filing info from title
                    # Format: "8-K - Company Name (0001234567) (Filer)"
                    title = entry.find('atom:title', ns)
                    title_text = title.text if title is not None else ""
                    
                    # Extract link (filing URL)
                    link = entry.find('atom:link', ns)
                    url = link.get('href', '') if link is not None else ""
                    
                    # Extract updated date
                    updated = entry.find('atom:updated', ns)
                    updated_text = updated.text if updated is not None else ""
                    filing_date = updated_text[:10] if updated_text else ""  # YYYY-MM-DD
                    
                    # Parse title to extract form type, company name, CIK
                    # Example: "8-K - Apple Inc. (0000320193) (Filer)"
                    parts = title_text.split(' - ', 1)
                    form_type = parts[0].strip() if parts else ""
                    
                    # Extract CIK from parentheses
                    cik = ""
                    company_name = ""
                    if len(parts) > 1:
                        rest = parts[1]
                        # Find CIK in format (0001234567)
                        import re
                        cik_match = re.search(r'\((\d{10})\)', rest)
                        if cik_match:
                            cik = cik_match.group(1)
                            # Company name is everything before the CIK
                            company_name = rest[:cik_match.start()].strip()
                    
                    # Extract accession number from URL
                    # Format: .../Archives/edgar/data/CIK/ACCESSION/...
                    accession = ""
                    if '/Archives/edgar/data/' in url:
                        url_parts = url.split('/')
                        for i, part in enumerate(url_parts):
                            if part == 'data' and i + 2 < len(url_parts):
                                accession = url_parts[i + 2]
                                break
                    
                    if cik:
                        filings.append(SECFiling(
                            cik=cik,
                            company_name=company_name,
                            form_type=form_type,
                            filing_date=filing_date,
                            accession_number=accession,
                            url=url
                        ))
                        
                except Exception as e:
                    logger.debug(f"[SECRSSClient] Error parsing entry: {e}")
                    continue
            
            return filings
            
        except ET.ParseError as e:
            logger.error(f"[SECRSSClient] XML parse error: {e}")
            return []
    
    def get_tickers_with_new_filings(
        self,
        form_type: str,
        since_date: Optional[str] = None,
        known_tickers: Optional[Set[str]] = None
    ) -> Set[str]:
        """
        Get ticker symbols for companies that have filed new documents.
        
        This is the main method for optimizing cache jobs - instead of
        checking all 5000 stocks, we only process the ones with new filings.
        
        Args:
            form_type: Filing type (8-K, 10-K, 10-Q, FORM4)
            since_date: Optional YYYY-MM-DD to only get filings after this date
            known_tickers: Optional set of our universe of tickers to filter to
            
        Returns:
            Set of ticker symbols with new filings
        """
        # Fetch recent filings
        filings = self.fetch_recent_filings(form_type, count=100, since_date=since_date)
        
        if not filings:
            return set()
        
        # Load CIK-to-ticker mapping
        cik_to_ticker = self._load_cik_to_ticker_mapping()
        
        # Convert CIKs to tickers
        tickers_with_filings = set()
        for filing in filings:
            ticker = cik_to_ticker.get(filing.cik)
            if ticker:
                # If we have a known universe, filter to it
                if known_tickers is None or ticker in known_tickers:
                    tickers_with_filings.add(ticker)
        
        logger.info(
            f"[SECRSSClient] Found {len(tickers_with_filings)} tickers with new {form_type} filings"
            f"{f' (filtered from {len(filings)} total filings)' if known_tickers else ''}"
        )
        
        return tickers_with_filings
    
    def get_filings_for_ticker(
        self,
        ticker: str,
        form_type: str,
        since_date: Optional[str] = None
    ) -> List[SECFiling]:
        """
        Get specific filings for a single ticker (for verification/debugging).
        
        Args:
            ticker: Stock ticker symbol
            form_type: Filing type (8-K, 10-K, 10-Q, FORM4)
            since_date: Optional cutoff date
            
        Returns:
            List of filings for this ticker
        """
        # Load mapping and get CIK
        cik_to_ticker = self._load_cik_to_ticker_mapping()
        
        # Find CIK for this ticker (inefficient but fine for single lookups)
        ticker_to_cik = {v: k for k, v in cik_to_ticker.items()}
        cik = ticker_to_cik.get(ticker.upper())
        
        if not cik:
            logger.warning(f"[SECRSSClient] No CIK found for ticker {ticker}")
            return []
        
        # Fetch filings and filter to this CIK
        filings = self.fetch_recent_filings(form_type, count=100, since_date=since_date)
        return [f for f in filings if f.cik == cik]


# Convenience function for testing
def test_rss_client():
    """Quick test of RSS client functionality"""
    import os
    user_agent = os.environ.get('SEC_USER_AGENT', 'Lynch Stock Screener test@example.com')
    
    client = SECRSSClient(user_agent)
    
    # Test fetching 8-K filings
    print("\n=== Recent 8-K Filings ===")
    filings = client.fetch_recent_filings('8-K', count=10)
    for f in filings[:5]:
        print(f"  {f.filing_date} | {f.form_type} | {f.company_name} (CIK: {f.cik})")
    
    # Test getting tickers with new 8-K filings
    print("\n=== Tickers with 8-K filings ===")
    tickers = client.get_tickers_with_new_filings('8-K')
    print(f"  {len(tickers)} tickers: {list(tickers)[:10]}...")
    
    # Test 10-K
    print("\n=== Recent 10-K Filings ===")
    tickers_10k = client.get_tickers_with_new_filings('10-K')
    print(f"  {len(tickers_10k)} tickers with 10-K filings")
    
    # Test Form 4
    print("\n=== Recent Form 4 Filings ===")
    tickers_form4 = client.get_tickers_with_new_filings('FORM4')
    print(f"  {len(tickers_form4)} tickers with Form 4 filings")


if __name__ == '__main__':
    test_rss_client()
