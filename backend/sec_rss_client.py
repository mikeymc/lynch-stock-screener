# ABOUTME: Client for fetching and parsing SEC EDGAR RSS feeds
# ABOUTME: Used to identify stocks with new filings without checking all symbols

import logging
import requests
import xml.etree.ElementTree as ET
from typing import Set, Dict, Optional
import re

logger = logging.getLogger(__name__)


class SECRSSClient:
    """
    Client for SEC EDGAR RSS feeds to identify stocks with recent filings.

    Used to optimize cache jobs by pre-filtering to only stocks with new filings,
    avoiding unnecessary API calls for stocks without recent activity.
    """

    RSS_BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
    NAMESPACE = {'atom': 'http://www.w3.org/2005/Atom'}

    # Map form types to SEC RSS feed parameters
    FORM_TYPE_MAPPING = {
        '8-K': '8-K',
        '10-K': '10-K',
        '10-Q': '10-Q',
        'FORM4': '4',  # Form 4 uses '4' in RSS
    }

    def __init__(self, user_agent: str):
        """
        Initialize SEC RSS client.

        Args:
            user_agent: User-Agent string (required by SEC)
        """
        self.user_agent = user_agent
        self.headers = {'User-Agent': user_agent}
        self._cik_to_ticker_cache: Optional[Dict[str, str]] = None

    def get_tickers_with_new_filings(self, form_type: str, known_tickers: Optional[Set[str]] = None) -> Set[str]:
        """
        Get ticker symbols that have new filings in the RSS feed.

        Args:
            form_type: Filing type ('8-K', '10-K', '10-Q', 'FORM4')
            known_tickers: Optional set of tickers to filter to (for efficiency)

        Returns:
            Set of ticker symbols with new filings
        """
        # Map form type to RSS parameter
        rss_form_type = self.FORM_TYPE_MAPPING.get(form_type)
        if not rss_form_type:
            logger.error(f"Unknown form type: {form_type}")
            return set()

        try:
            # Fetch RSS feed
            url = f"{self.RSS_BASE_URL}?action=getcurrent&type={rss_form_type}&output=atom"
            logger.info(f"Fetching SEC RSS feed for {form_type}: {url}")

            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)
            entries = root.findall('atom:entry', self.NAMESPACE)

            logger.info(f"Found {len(entries)} {form_type} filings in RSS feed")

            # Extract CIKs from entries
            ciks = set()
            for entry in entries:
                title = entry.find('atom:title', self.NAMESPACE)
                if title is not None and title.text:
                    # Extract CIK from title format: "8-K - COMPANY NAME (CIK) (Filer)"
                    cik_match = re.search(r'\((\d+)\)', title.text)
                    if cik_match:
                        cik = cik_match.group(1).zfill(10)  # Pad to 10 digits
                        ciks.add(cik)

            logger.info(f"Extracted {len(ciks)} unique CIKs from RSS feed")

            # Map CIKs to tickers
            tickers = self._map_ciks_to_tickers(ciks, known_tickers)

            logger.info(f"Mapped to {len(tickers)} tickers with new {form_type} filings")
            return tickers

        except Exception as e:
            logger.error(f"Error fetching RSS feed for {form_type}: {e}")
            import traceback
            traceback.print_exc()
            return set()

    def get_tickers_with_new_filings_paginated(self, form_type: str, known_tickers: Optional[Set[str]], db) -> Set[str]:
        """
        Get ticker symbols with new filings using RSS pagination.

        Paginates through RSS feed, checking each filing against the database.
        Stops when hitting a known filing (we're caught up) or max limit.

        Args:
            form_type: Filing type ('8-K', '10-K', '10-Q', 'FORM4')
            known_tickers: Optional set of tickers to filter to
            db: Database instance for checking existing filings

        Returns:
            Set of ticker symbols with new filings
        """
        # Map form type to RSS parameter
        rss_form_type = self.FORM_TYPE_MAPPING.get(form_type)
        if not rss_form_type:
            logger.error(f"Unknown form type: {form_type}")
            return set()

        start = 0
        batch_size = 100
        max_filings = 1000  # Safety limit
        new_ciks = set()
        total_checked = 0

        logger.info(f"Starting paginated RSS fetch for {form_type}")

        try:
            while start < max_filings:
                # Fetch RSS page with pagination
                url = f"{self.RSS_BASE_URL}?action=getcurrent&type={rss_form_type}&start={start}&count={batch_size}&output=atom"
                logger.info(f"Fetching RSS page: start={start}, count={batch_size}")

                response = requests.get(url, headers=self.headers, timeout=10)
                response.raise_for_status()

                # Parse XML
                root = ET.fromstring(response.content)
                entries = root.findall('atom:entry', self.NAMESPACE)

                if not entries:
                    logger.info(f"No more entries in RSS feed (checked {total_checked} filings)")
                    break

                logger.info(f"Processing {len(entries)} entries from RSS page")

                for entry in entries:
                    total_checked += 1

                    # Extract accession number and CIK from entry
                    # Format: urn:tag:sec.gov,2008:accession-number=0001628280-26-003909
                    id_elem = entry.find('atom:id', self.NAMESPACE)
                    if id_elem is None or not id_elem.text:
                        continue

                    accession_match = re.search(r'accession-number=([0-9\-]+)', id_elem.text)
                    if not accession_match:
                        continue

                    accession_number = accession_match.group(1)

                    # For Form 4, extract ticker for fallback check (old data has NULL accession_number)
                    ticker = None
                    if form_type == 'FORM4':
                        title = entry.find('atom:title', self.NAMESPACE)
                        if title is not None and title.text:
                            cik_match = re.search(r'\((\d+)\)', title.text)
                            if cik_match:
                                cik = cik_match.group(1).zfill(10)
                                # Load CIK mapping if needed
                                if self._cik_to_ticker_cache is None:
                                    self._cik_to_ticker_cache = self._load_cik_to_ticker_mapping()
                                ticker = self._cik_to_ticker_cache.get(cik)

                    # Check if we already have this filing
                    if db.filing_exists(accession_number, form_type, ticker=ticker):
                        logger.info(f"Hit known filing {accession_number} after checking {total_checked} filings - stopping pagination")
                        return self._map_ciks_to_tickers(new_ciks, known_tickers)

                    # Extract CIK from title and add to new filings set
                    title = entry.find('atom:title', self.NAMESPACE)
                    if title is not None and title.text:
                        cik_match = re.search(r'\((\d+)\)', title.text)
                        if cik_match:
                            cik = cik_match.group(1).zfill(10)
                            new_ciks.add(cik)

                # Fetch next page
                start += batch_size

            # Reached end of RSS or max limit without hitting known filing
            logger.info(f"Paginated through {total_checked} filings without hitting known filing (or reached max limit)")
            return self._map_ciks_to_tickers(new_ciks, known_tickers)

        except Exception as e:
            logger.error(f"Error during paginated RSS fetch for {form_type}: {e}")
            import traceback
            traceback.print_exc()
            # Return what we found so far
            return self._map_ciks_to_tickers(new_ciks, known_tickers)

    def _map_ciks_to_tickers(self, ciks: Set[str], known_tickers: Optional[Set[str]] = None) -> Set[str]:
        """
        Map CIK numbers to ticker symbols.

        Args:
            ciks: Set of CIK numbers
            known_tickers: Optional set of tickers to filter to

        Returns:
            Set of ticker symbols
        """
        # Load CIK-to-ticker mapping
        if self._cik_to_ticker_cache is None:
            self._cik_to_ticker_cache = self._load_cik_to_ticker_mapping()

        # Map CIKs to tickers
        tickers = set()
        for cik in ciks:
            ticker = self._cik_to_ticker_cache.get(cik)
            if ticker:
                # Filter to known tickers if provided
                if known_tickers is None or ticker in known_tickers:
                    tickers.add(ticker)

        return tickers

    def _load_cik_to_ticker_mapping(self) -> Dict[str, str]:
        """
        Load CIK-to-ticker mapping from SEC.

        Returns:
            Dictionary mapping CIK (10-digit string) to ticker symbol
        """
        try:
            url = "https://www.sec.gov/files/company_tickers.json"
            logger.info(f"Loading CIK-to-ticker mapping from SEC")

            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build reverse mapping (CIK -> ticker)
            mapping = {}
            for entry in data.values():
                ticker = entry.get('ticker', '').upper()
                cik = str(entry.get('cik_str', '')).zfill(10)
                mapping[cik] = ticker

            logger.info(f"Loaded CIK-to-ticker mapping for {len(mapping)} companies")
            return mapping

        except Exception as e:
            logger.error(f"Error loading CIK-to-ticker mapping: {e}")
            import traceback
            traceback.print_exc()
            return {}
