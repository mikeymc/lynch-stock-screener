# ABOUTME: Core EdgarFetcher class with initialization, rate limiting, CIK lookups, and API fetching
# ABOUTME: Provides the fundamental infrastructure that all mixin classes depend on via self

import requests
import time
import logging
from typing import Dict, List, Optional, Any
from edgar import Company, set_identity
from sec_rate_limiter import SEC_RATE_LIMITER
import hishel

logger = logging.getLogger(__name__)


class EdgarFetcherCore:
    """Fetches stock fundamentals from SEC EDGAR database"""

    BASE_URL = "https://data.sec.gov"
    TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
    COMPANY_FACTS_URL = f"{BASE_URL}/api/xbrl/companyfacts/CIK{{cik}}.json"

    def __init__(self, user_agent: str, use_bulk_cache: bool = True, cache_dir: str = "./sec_cache", db=None, cik_cache: Dict[str, str] = None):
        """
        Initialize EDGAR fetcher with required User-Agent header

        Args:
            user_agent: User-Agent string in format "Company Name email@example.com"
            use_bulk_cache: Whether to use PostgreSQL cache (default: True)
            cache_dir: Deprecated - kept for backwards compatibility
            db: Optional Database instance for querying company_facts
            cik_cache: Optional pre-loaded ticker-to-CIK mapping to avoid HTTP calls
        """
        self.user_agent = user_agent
        self.headers = {
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate'
        }
        # Use pre-loaded cache if provided, otherwise will be loaded on first use
        self.ticker_to_cik_cache = cik_cache
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 10 requests per second max

        # Use PostgreSQL for SEC data
        self.use_bulk_cache = use_bulk_cache
        self.db = db

        # Cache for edgartools Company objects to avoid redundant SEC calls
        # Key: CIK, Value: Company object
        self._company_cache: Dict[str, Company] = {}

        # Set identity for edgartools
        set_identity(user_agent)

    def initialize_sec_cache(self, force: bool = False) -> bool:
        """
        Initialize or update the SEC bulk data cache

        Args:
            force: Force re-download even if cache is valid

        Returns:
            True if successful, False otherwise
        """
        if not self.bulk_manager:
            logger.error("Bulk cache is disabled")
            return False

        if not force and self.bulk_manager.is_cache_valid():
            logger.info("SEC cache is already valid, skipping download")
            stats = self.bulk_manager.get_cache_stats()
            logger.info(f"Cache stats: {stats}")
            return True

        logger.info("Initializing SEC bulk data cache...")
        return self.bulk_manager.download_and_extract()

    def _rate_limit(self, caller: str = "edgar"):
        """Enforce rate limiting of 10 requests per second using global limiter"""
        # Use global rate limiter to coordinate across all threads
        SEC_RATE_LIMITER.acquire(caller=caller)

    @staticmethod
    def prefetch_cik_cache(user_agent: str) -> Dict[str, str]:
        """
        Pre-fetch ticker-to-CIK mapping from SEC.

        Call this once at worker startup and pass the result to EdgarFetcher instances.
        This avoids multiple EdgarFetcher instances each making their own HTTP call.

        Args:
            user_agent: User-Agent string in format "Company Name email@example.com"

        Returns:
            Dictionary mapping ticker symbols to CIK numbers
        """
        headers = {
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate'
        }
        url = "https://www.sec.gov/files/company_tickers.json"

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build mapping dictionary
            mapping = {}
            for entry in data.values():
                ticker = entry.get('ticker', '').upper()
                cik = str(entry.get('cik_str', '')).zfill(10)
                mapping[ticker] = cik

            logger.info(f"[EdgarFetcher] Pre-fetched CIK mappings for {len(mapping)} tickers")
            return mapping

        except Exception as e:
            logger.error(f"[EdgarFetcher] Error pre-fetching CIK mappings: {e}")
            return {}

    def get_company(self, cik: str) -> Optional[Company]:
        """
        Get or create a cached edgartools Company object.

        This caches Company objects to avoid redundant SEC API calls when
        the same company is accessed multiple times (e.g., for 10-K and 10-Q extraction).

        Args:
            cik: 10-digit CIK number

        Returns:
            Cached Company object or None if creation fails
        """
        if cik in self._company_cache:
            logger.debug(f"[CIK {cik}] Using cached Company object")
            return self._company_cache[cik]

        try:
            # Rate limit before edgartools makes HTTP requests
            self._rate_limit(caller=f"Company-{cik}")
            company = Company(cik)
            self._company_cache[cik] = company
            logger.debug(f"[CIK {cik}] Created and cached Company object")
            return company
        except Exception as e:
            logger.error(f"[CIK {cik}] Error creating Company object: {e}")
            return None

    def _load_ticker_to_cik_mapping(self) -> Dict[str, str]:
        """Load ticker-to-CIK mapping from SEC"""
        if self.ticker_to_cik_cache is not None:
            return self.ticker_to_cik_cache

        try:
            self._rate_limit(caller="cik-mapping")
            response = requests.get(self.TICKER_CIK_URL, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build mapping dictionary
            mapping = {}
            for entry in data.values():
                ticker = entry.get('ticker', '').upper()
                cik = str(entry.get('cik_str', '')).zfill(10)
                mapping[ticker] = cik

            self.ticker_to_cik_cache = mapping
            return mapping

        except Exception as e:
            logger.error(f"Error loading ticker-to-CIK mapping from EDGAR: {e}")
            import traceback
            traceback.print_exc()
            # Return empty mapping to allow fallback to yfinance
            self.ticker_to_cik_cache = {}
            return {}

    def get_cik_for_ticker(self, ticker: str) -> Optional[str]:
        """
        Convert ticker symbol to CIK number

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')

        Returns:
            10-digit CIK string or None if not found
        """
        mapping = self._load_ticker_to_cik_mapping()
        cik = mapping.get(ticker.upper())
        if cik:
            logger.info(f"[SECDataFetcher][{ticker}] Found CIK: {cik}")
        else:
            logger.debug(f"[{ticker}] CIK not found in EDGAR mapping")
        return cik

    def fetch_company_facts(self, cik: str) -> Optional[Dict[str, Any]]:
        """
        Fetch company facts from PostgreSQL cache or SEC EDGAR API

        Tries PostgreSQL company_facts table first, falls back to API if not found.

        Args:
            cik: 10-digit CIK number

        Returns:
            Dictionary containing company facts data or None on error
        """
        # Try PostgreSQL cache first
        if self.use_bulk_cache and self.db:
            conn = None
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT facts FROM company_facts WHERE cik = %s
                """, (cik,))
                row = cursor.fetchone()

                if row and row[0]:
                    logger.info(f"[CIK {cik}] Loaded company facts from PostgreSQL")
                    return row[0]  # JSONB is automatically deserialized
                else:
                    logger.warning(f"⚠️  [CIK {cik}] NOT IN PostgreSQL - Falling back to slow SEC API call")
            except Exception as e:
                logger.error(f"[CIK {cik}] Error querying PostgreSQL: {e}")
            finally:
                if conn:
                    self.db.return_connection(conn)

        # Fallback to API
        logger.warning(f"⚠️  [CIK {cik}] Making slow SEC API request...")
        return self._fetch_from_api(cik)

    def _fetch_from_api(self, cik: str) -> Optional[Dict[str, Any]]:
        """
        Fetch company facts from SEC EDGAR API with retry logic for SSL errors

        Args:
            cik: 10-digit CIK number

        Returns:
            Dictionary containing company facts data or None on error
        """
        self._rate_limit(caller=f"facts-{cik}")

        url = self.COMPANY_FACTS_URL.format(cik=cik)

        # Retry logic for transient SSL errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=self.headers, timeout=30)  # Increased timeout for Fly.io
                response.raise_for_status()
                logger.info(f"[CIK {cik}] Successfully fetched company facts from EDGAR API")
                return response.json()
            except requests.exceptions.SSLError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"[CIK {cik}] SSL error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"[CIK {cik}] SSL error after {max_retries} attempts: {e}")
                    return None
            except requests.exceptions.RequestException as e:
                logger.error(f"[CIK {cik}] Error fetching company facts: {type(e).__name__}: {e}")
                return None
