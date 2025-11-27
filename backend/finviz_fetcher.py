# ABOUTME: Fetches institutional ownership data in bulk from Finviz screener
# ABOUTME: Provides fast alternative to individual yfinance API calls

import requests
from bs4 import BeautifulSoup
import time
import logging
import json
from typing import Dict, Optional
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class FinvizFetcher:
    """Fetches institutional ownership data from Finviz screener in bulk"""

    BASE_URL = "https://finviz.com/screener.ashx"
    CACHE_FILE = "finviz_institutional_cache.json"
    CACHE_VALIDITY_DAYS = 30

    def __init__(self, cache_dir: str = "./"):
        """
        Initialize Finviz fetcher

        Args:
            cache_dir: Directory to store cache file (default: current directory)
        """
        self.cache_dir = cache_dir
        self.cache_path = os.path.join(cache_dir, self.CACHE_FILE)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def fetch_all_institutional_ownership(self, limit: int = 10000, use_cache: bool = True) -> Dict[str, float]:
        """
        Fetch institutional ownership % for all stocks from Finviz screener

        Args:
            limit: Maximum number of stocks to fetch (default: 10000)
            use_cache: Whether to use cached data if available and fresh (default: True)

        Returns:
            Dictionary mapping symbol to institutional ownership decimal
            e.g., {'AAPL': 0.672, 'MSFT': 0.718, ...}
        """
        # Check cache first
        if use_cache:
            cached_data = self._load_cache()
            if cached_data is not None:
                logger.info(f"Using cached Finviz institutional ownership data ({len(cached_data)} stocks)")
                return cached_data

        logger.info(f"Fetching institutional ownership for up to {limit} stocks from Finviz...")

        result = {}
        stocks_per_page = 20
        total_fetched = 0
        empty_pages = 0  # Track consecutive empty pages

        # Finviz pagination: r=1, r=21, r=41, etc.
        for start_row in range(1, limit, stocks_per_page):
            try:
                # Fetch page
                page_data = self._fetch_page(start_row)

                if page_data:
                    # Add to result
                    result.update(page_data)
                    total_fetched += len(page_data)
                    logger.info(f"Fetched page at row {start_row}: {len(page_data)} stocks (total: {total_fetched})")
                else:
                    # Empty page - could mean end of data OR all stocks on page have no data
                    # Check if we've gone 5 pages without any data - then stop
                    empty_pages += 1
                    logger.debug(f"Empty page at row {start_row} ({empty_pages} consecutive empty pages)")

                    if empty_pages >= 5:
                        logger.info(f"Reached end of data at row {start_row} (5 consecutive empty pages)")
                        break

                # Reset empty page counter if we got data
                if page_data:
                    empty_pages = 0

                # Polite delay between requests (0.5 seconds)
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error fetching page at row {start_row}: {e}")
                # Continue with next page rather than failing completely
                continue

        logger.info(f"✓ Fetched institutional ownership for {len(result)} stocks from Finviz")

        # Save to cache
        self._save_cache(result)

        return result

    def _fetch_page(self, start_row: int) -> Dict[str, float]:
        """
        Fetch a single page of Finviz screener data

        Args:
            start_row: Starting row number (1, 21, 41, etc.)

        Returns:
            Dictionary mapping symbol to institutional ownership for this page
        """
        params = {
            'v': '131',  # Ownership view
            'r': str(start_row),
            'f': 'cap_smallover',  # Filter: Market cap > $300M (gets real companies, not penny stocks)
            'o': '-marketcap'  # Order by market cap descending (largest first)
        }

        try:
            response = requests.get(self.BASE_URL, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()

            # Parse HTML
            return self._parse_table(response.text)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.error("❌ Finviz returned 403 Forbidden - possible IP ban or rate limit")
                raise
            elif e.response.status_code == 429:
                logger.warning(f"⚠️  Rate limited by Finviz, waiting 5 seconds...")
                time.sleep(5)
                # Retry once
                response = requests.get(self.BASE_URL, params=params, headers=self.headers, timeout=10)
                response.raise_for_status()
                return self._parse_table(response.text)
            else:
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching Finviz page: {e}")
            raise

    def _parse_table(self, html: str) -> Dict[str, float]:
        """
        Parse Finviz screener table HTML to extract institutional ownership

        Args:
            html: Raw HTML from Finviz screener page

        Returns:
            Dictionary mapping symbol to institutional ownership
        """
        soup = BeautifulSoup(html, 'lxml')
        result = {}

        # Find the screener table
        # Finviz uses a table with class 'table-light' or similar
        # The structure is: <tr valign='top'> rows containing stock data
        rows = soup.find_all('tr', {'valign': 'top'})

        if not rows:
            logger.warning("No data rows found in Finviz page")
            return result

        for row in rows:
            cols = row.find_all('td')

            # Finviz ownership view (v=131) has columns:
            # 0: No., 1: Ticker, 2: Market Cap, 3: Outstanding, 4: Float,
            # 5: Insider Own, 6: Insider Trans, 7: Inst Own, 8: Inst Trans,
            # 9: Float Short, 10: Short Ratio, 11: Avg Volume, 12: Price, 13: Change, 14: Volume

            if len(cols) < 8:
                # Not enough columns, skip this row
                continue

            try:
                # Extract ticker (column 1)
                ticker_elem = cols[1].find('a')
                if not ticker_elem:
                    continue
                ticker = ticker_elem.text.strip()

                # Extract institutional ownership (column 7)
                inst_own_text = cols[7].text.strip()

                # Parse percentage: "67.21%" -> 0.6721
                if inst_own_text and inst_own_text != '-':
                    # Remove '%' and convert to decimal
                    inst_own_pct = inst_own_text.replace('%', '')
                    inst_own_decimal = float(inst_own_pct) / 100.0
                    result[ticker] = inst_own_decimal

            except (ValueError, IndexError, AttributeError) as e:
                logger.debug(f"Error parsing row: {e}")
                continue

        return result

    def _load_cache(self) -> Optional[Dict[str, float]]:
        """
        Load institutional ownership data from cache file if valid

        Returns:
            Cached data dict or None if cache is invalid/missing
        """
        if not os.path.exists(self.cache_path):
            logger.info("No Finviz cache file found")
            return None

        try:
            with open(self.cache_path, 'r') as f:
                cache = json.load(f)

            # Check cache age
            timestamp = datetime.fromisoformat(cache['timestamp'])
            age = datetime.now() - timestamp

            if age > timedelta(days=self.CACHE_VALIDITY_DAYS):
                logger.info(f"Finviz cache is stale ({age.days} days old, max {self.CACHE_VALIDITY_DAYS} days)")
                return None

            logger.info(f"Finviz cache is valid ({age.days} days old)")
            return cache['data']

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Error loading Finviz cache: {e}")
            return None

    def _save_cache(self, data: Dict[str, float]) -> None:
        """
        Save institutional ownership data to cache file

        Args:
            data: Dictionary mapping symbol to institutional ownership
        """
        cache = {
            'timestamp': datetime.now().isoformat(),
            'data': data,
            'count': len(data)
        }

        try:
            with open(self.cache_path, 'w') as f:
                json.dump(cache, f, indent=2)

            logger.info(f"✓ Saved Finviz cache to {self.cache_path} ({len(data)} stocks)")

        except IOError as e:
            logger.error(f"Error saving Finviz cache: {e}")
