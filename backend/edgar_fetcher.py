# ABOUTME: Fetches financial data from SEC EDGAR API using CIK lookups
# ABOUTME: Provides historical EPS, revenue, and debt metrics from 10-K filings

import requests
import time
import logging
from typing import Dict, List, Optional, Any
from edgar import Company, set_identity
from sec_rate_limiter import SEC_RATE_LIMITER

logger = logging.getLogger(__name__)


class EdgarFetcher:
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

    def parse_eps_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract EPS history from company facts (supports both US-GAAP and IFRS)

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, eps, and fiscal_end values
        """
        eps_data_list = None

        # Try US-GAAP first (domestic companies)
        try:
            eps_units = company_facts['facts']['us-gaap']['EarningsPerShareDiluted']['units']
            if 'USD/shares' in eps_units:
                eps_data_list = eps_units['USD/shares']
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS (foreign companies filing 20-F)
        if eps_data_list is None:
            try:
                eps_units = company_facts['facts']['ifrs-full']['DilutedEarningsLossPerShare']['units']

                # Prefer USD if available, otherwise use any currency
                if 'USD/shares' in eps_units:
                    eps_data_list = eps_units['USD/shares']
                else:
                    # Find first unit matching */shares pattern
                    share_units = [u for u in eps_units.keys() if u.endswith('/shares')]
                    if share_units:
                        eps_data_list = eps_units[share_units[0]]
            except (KeyError, TypeError):
                pass

        # If we still don't have data, return empty
        if eps_data_list is None:
            logger.debug("Could not parse EPS history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Filter for annual reports (10-K for US, 20-F for foreign)
        # Use dict to keep only the latest fiscal_end for each year
        annual_eps_by_year = {}

        for entry in eps_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fiscal_end = entry.get('end')
                # Extract year from fiscal_end date (more reliable than fy field)
                year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
                eps = entry.get('val')

                if year and eps and fiscal_end:
                    # Keep the entry with the latest fiscal_end for each year
                    if year not in annual_eps_by_year or fiscal_end > annual_eps_by_year[year]['fiscal_end']:
                        annual_eps_by_year[year] = {
                            'year': year,
                            'eps': eps,
                            'fiscal_end': fiscal_end
                        }

        # Convert dict to list and sort by year descending
        annual_eps = list(annual_eps_by_year.values())
        annual_eps.sort(key=lambda x: x['year'], reverse=True)
        logger.info(f"Successfully parsed {len(annual_eps)} years of EPS data from EDGAR")
        return annual_eps

    def parse_quarterly_eps_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract quarterly EPS history from company facts (supports both US-GAAP and IFRS)

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter, eps, and fiscal_end values
        """
        eps_data_list = None

        # Try US-GAAP first (domestic companies)
        try:
            eps_units = company_facts['facts']['us-gaap']['EarningsPerShareDiluted']['units']
            if 'USD/shares' in eps_units:
                eps_data_list = eps_units['USD/shares']
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS (foreign companies filing 6-K)
        if eps_data_list is None:
            try:
                eps_units = company_facts['facts']['ifrs-full']['DilutedEarningsLossPerShare']['units']

                # Prefer USD if available, otherwise use any currency
                if 'USD/shares' in eps_units:
                    eps_data_list = eps_units['USD/shares']
                else:
                    # Find first unit matching */shares pattern
                    share_units = [u for u in eps_units.keys() if u.endswith('/shares')]
                    if share_units:
                        eps_data_list = eps_units[share_units[0]]
            except (KeyError, TypeError):
                pass

        # If we still don't have data, return empty
        if eps_data_list is None:
            logger.debug("Could not parse quarterly EPS history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Filter for quarterly reports (10-Q for US, 6-K for foreign)
        quarterly_eps = []
        seen_quarters = set()

        for entry in eps_data_list:
            if entry.get('form') in ['10-Q', '6-K']:
                fiscal_end = entry.get('end')
                # Extract year from fiscal_end date (more reliable than fy field)
                year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
                quarter = entry.get('fp')  # Fiscal period: Q1, Q2, Q3
                eps = entry.get('val')

                # Only include entries with fiscal period (Q1, Q2, Q3)
                # Avoid duplicates using (year, quarter) tuple
                if year and quarter and eps and (year, quarter) not in seen_quarters:
                    quarterly_eps.append({
                        'year': year,
                        'quarter': quarter,
                        'eps': eps,
                        'fiscal_end': fiscal_end
                    })
                    seen_quarters.add((year, quarter))

        # Sort by year descending, then by quarter
        def quarter_sort_key(entry):
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            return (-entry['year'], quarter_order.get(entry['quarter'], 0))

        quarterly_eps.sort(key=quarter_sort_key)
        logger.info(f"Successfully parsed {len(quarterly_eps)} quarters of EPS data from EDGAR")
        return quarterly_eps

    def parse_net_income_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract Net Income history from company facts (split-independent metric)

        Net Income (total earnings in USD) is NOT affected by stock splits,
        unlike EPS which drops artificially at split events. This makes Net Income
        the correct base metric for calculating our own split-adjusted EPS.

        Supports both US-GAAP (domestic companies) and IFRS (foreign companies).

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, net_income, and fiscal_end values
        """
        net_income_data_list = None

        # Try US-GAAP first (domestic companies)
        try:
            ni_units = company_facts['facts']['us-gaap']['NetIncomeLoss']['units']
            if 'USD' in ni_units:
                net_income_data_list = ni_units['USD']
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS (foreign companies filing 20-F)
        if net_income_data_list is None:
            try:
                ni_units = company_facts['facts']['ifrs-full']['ProfitLoss']['units']

                # Prefer USD if available, otherwise use any currency
                if 'USD' in ni_units:
                    net_income_data_list = ni_units['USD']
                else:
                    # Find first currency unit (3-letter code)
                    currency_units = [u for u in ni_units.keys() if len(u) == 3 and u.isupper()]
                    if currency_units:
                        net_income_data_list = ni_units[currency_units[0]]
            except (KeyError, TypeError):
                pass

        # If we still don't have data, return empty
        if net_income_data_list is None:
            logger.debug("Could not parse Net Income history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Filter for annual reports (10-K for US, 20-F for foreign)
        # Use dict to keep only the highest net_income for each fiscal year
        annual_net_income_by_year = {}

        for entry in net_income_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fiscal_end = entry.get('end')
                frame = entry.get('frame', '')
                net_income = entry.get('val')

                # Skip quarterly entries (frames ending in Q1, Q2, Q3, Q4)
                if frame and frame.endswith(('Q1', 'Q2', 'Q3', 'Q4')):
                    continue

                if net_income is not None and fiscal_end:
                    # Use fiscal_end year as the key (this is the actual fiscal year)
                    year = int(fiscal_end[:4])

                    # Group by unique fiscal_end dates, keep highest absolute value
                    if fiscal_end not in annual_net_income_by_year:
                        annual_net_income_by_year[fiscal_end] = {
                            'year': year,
                            'net_income': net_income,
                            'fiscal_end': fiscal_end
                        }
                    elif abs(net_income) > abs(annual_net_income_by_year[fiscal_end]['net_income']):
                        # Keep highest absolute value (in case of duplicates)
                        annual_net_income_by_year[fiscal_end] = {
                            'year': year,
                            'net_income': net_income,
                            'fiscal_end': fiscal_end
                        }

        # Group by year, keeping highest absolute value per year
        # (This handles cases where multiple fiscal_end dates map to same year)
        by_year = {}
        for fiscal_end, entry in annual_net_income_by_year.items():
            year = entry['year']
            if year not in by_year:
                by_year[year] = entry
            elif abs(entry['net_income']) > abs(by_year[year]['net_income']):
                by_year[year] = entry

        # Convert dict to list and sort by year descending
        annual_net_income = list(by_year.values())
        annual_net_income.sort(key=lambda x: x['year'], reverse=True)
        logger.info(f"Successfully parsed {len(annual_net_income)} years of Net Income data from EDGAR")
        return annual_net_income

    def parse_cash_flow_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract Cash Flow history (Operating Cash Flow and CapEx) from company facts.
        Calculates Free Cash Flow (FCF) = OCF - CapEx.

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, operating_cash_flow, capital_expenditures, free_cash_flow, and fiscal_end
        """
        # 1. Extract Operating Cash Flow (NetCashProvidedByUsedInOperatingActivities)
        ocf_data = []
        try:
            # Try US-GAAP - try multiple tag variations
            if 'us-gaap' in company_facts['facts']:
                # Standard tag
                if 'NetCashProvidedByUsedInOperatingActivities' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['NetCashProvidedByUsedInOperatingActivities']['units']
                    if 'USD' in units:
                        ocf_data.extend(units['USD'])

                # Alternative tag - continuing operations (used by AAPL 2014 and others)
                if 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['NetCashProvidedByUsedInOperatingActivitiesContinuingOperations']['units']
                    if 'USD' in units:
                        ocf_data.extend(units['USD'])

            # Try IFRS if no US-GAAP data found
            elif 'ifrs-full' in company_facts['facts'] and 'CashFlowsFromUsedInOperatingActivities' in company_facts['facts']['ifrs-full']:
                 units = company_facts['facts']['ifrs-full']['CashFlowsFromUsedInOperatingActivities']['units']
                 # Find USD or first currency
                 if 'USD' in units:
                     ocf_data = units['USD']
                 else:
                     currency_units = [u for u in units.keys() if len(u) == 3 and u.isupper()]
                     if currency_units:
                         ocf_data = units[currency_units[0]]
        except (KeyError, TypeError):
            pass

        # 2. Extract Capital Expenditures (PaymentsToAcquirePropertyPlantAndEquipment)
        capex_data = []
        try:
            # Try US-GAAP
            if 'us-gaap' in company_facts['facts']:
                # Standard tag
                if 'PaymentsToAcquirePropertyPlantAndEquipment' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['PaymentsToAcquirePropertyPlantAndEquipment']['units']
                    if 'USD' in units:
                        capex_data.extend(units['USD'])
                
                # Alternative tag (used by AMZN and others)
                if 'PaymentsToAcquireProductiveAssets' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['PaymentsToAcquireProductiveAssets']['units']
                    if 'USD' in units:
                        capex_data.extend(units['USD'])

            # Try IFRS
            elif 'ifrs-full' in company_facts['facts'] and 'CashFlowsUsedInObtainingControlOfSubsidiariesOrOtherBusinessesClassifiedAsInvestingActivities' in company_facts['facts']['ifrs-full']:
                # Note: IFRS CapEx mapping is tricky, often PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities
                # Let's try PurchaseOfPropertyPlantAndEquipment
                if 'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities' in company_facts['facts']['ifrs-full']:
                     units = company_facts['facts']['ifrs-full']['PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities']['units']
                     if 'USD' in units:
                         capex_data = units['USD']
                     else:
                         currency_units = [u for u in units.keys() if len(u) == 3 and u.isupper()]
                         if currency_units:
                             capex_data = units[currency_units[0]]
        except (KeyError, TypeError):
            pass

        # Helper to process annual data
        def process_annual_data(data_list):
            by_year = {}
            for entry in data_list:
                if entry.get('form') in ['10-K', '20-F']:
                    fiscal_end = entry.get('end')
                    year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
                    val = entry.get('val')
                    if year and val is not None and fiscal_end:
                        if year not in by_year or fiscal_end > by_year[year]['fiscal_end']:
                            by_year[year] = {'val': val, 'fiscal_end': fiscal_end}
            return by_year

        ocf_by_year = process_annual_data(ocf_data)
        capex_by_year = process_annual_data(capex_data)

        # 3. Extract Net PPE and Depreciation for derived CapEx fallback
        # This is used when direct CapEx tags are missing (e.g., NVDA 2013-2021)
        ppe_net_data = []
        deprec_data = []
        try:
            if 'us-gaap' in company_facts['facts']:
                # Net PPE
                if 'PropertyPlantAndEquipmentNet' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['PropertyPlantAndEquipmentNet']['units']
                    if 'USD' in units:
                        ppe_net_data = units['USD']
                
                # Depreciation (preferred over DepreciationAndAmortization for accuracy)
                if 'Depreciation' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['Depreciation']['units']
                    if 'USD' in units:
                        deprec_data = units['USD']
                elif 'DepreciationAndAmortization' in company_facts['facts']['us-gaap']:
                    # Fallback to D&A if pure Depreciation not available
                    units = company_facts['facts']['us-gaap']['DepreciationAndAmortization']['units']
                    if 'USD' in units:
                        deprec_data = units['USD']
        except (KeyError, TypeError):
            pass

        ppe_net_by_year = process_annual_data(ppe_net_data)
        deprec_by_year = process_annual_data(deprec_data)

        # Combine into result
        cash_flow_history = []
        all_years = set(ocf_by_year.keys()) | set(capex_by_year.keys())

        for year in all_years:
            ocf = ocf_by_year.get(year, {}).get('val')
            capex = capex_by_year.get(year, {}).get('val')
            fiscal_end = ocf_by_year.get(year, {}).get('fiscal_end') or capex_by_year.get(year, {}).get('fiscal_end')

            # If CapEx is missing, try to derive it: CapEx ≈ ΔNetPPE + Depreciation
            if capex is None:
                net_ppe_curr = ppe_net_by_year.get(year, {}).get('val')
                net_ppe_prev = ppe_net_by_year.get(year - 1, {}).get('val')
                deprec = deprec_by_year.get(year, {}).get('val')
                
                if net_ppe_curr is not None and net_ppe_prev is not None and deprec is not None:
                    derived_capex = (net_ppe_curr - net_ppe_prev) + deprec
                    # Sanity check: CapEx should generally be positive
                    # Large negatives imply divestitures which aren't CapEx
                    if derived_capex > -1_000_000:
                        capex = derived_capex
                        logger.debug(f"[Year {year}] Derived CapEx from PPE delta: ${capex:,.0f}")

            # Calculate FCF
            fcf = None
            if ocf is not None and capex is not None:
                fcf = ocf - capex

            cash_flow_history.append({
                'year': year,
                'operating_cash_flow': ocf,
                'capital_expenditures': capex,
                'free_cash_flow': fcf,
                'fiscal_end': fiscal_end
            })

        cash_flow_history.sort(key=lambda x: x['year'], reverse=True)
        logger.info(f"Successfully parsed {len(cash_flow_history)} years of Cash Flow data")
        return cash_flow_history

    def parse_quarterly_net_income_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract quarterly Net Income history with Q4 calculated from annual data

        EDGAR provides quarterly data in 10-Q filings (Q1, Q2, Q3) but Q4 is
        typically only reported in the annual 10-K. We calculate Q4 as:
        Q4 = Annual Net Income - (Q1 + Q2 + Q3)

        Supports both US-GAAP (domestic companies) and IFRS (foreign companies).

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter, net_income, and fiscal_end values
        """
        net_income_data_list = None

        # Try US-GAAP first (domestic companies)
        try:
            ni_units = company_facts['facts']['us-gaap']['NetIncomeLoss']['units']
            if 'USD' in ni_units:
                net_income_data_list = ni_units['USD']
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS (foreign companies filing 6-K)
        if net_income_data_list is None:
            try:
                ni_units = company_facts['facts']['ifrs-full']['ProfitLoss']['units']

                # Prefer USD if available, otherwise use any currency
                if 'USD' in ni_units:
                    net_income_data_list = ni_units['USD']
                else:
                    # Find first currency unit (3-letter code)
                    currency_units = [u for u in ni_units.keys() if len(u) == 3 and u.isupper()]
                    if currency_units:
                        net_income_data_list = ni_units[currency_units[0]]
            except (KeyError, TypeError):
                pass

        # If we still don't have data, return empty
        if net_income_data_list is None:
            logger.debug("Could not parse quarterly Net Income history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Extract Q1, Q2, Q3 from quarterly reports (10-Q for US, 6-K for foreign)
        quarterly_net_income = []
        seen_quarters = set()

        for entry in net_income_data_list:
            if entry.get('form') in ['10-Q', '6-K']:
                fiscal_end = entry.get('end')
                # Extract year from fiscal_end date (more reliable than fy field)
                year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
                quarter = entry.get('fp')  # Fiscal period: Q1, Q2, Q3
                net_income = entry.get('val')

                # Only include entries with fiscal period (Q1, Q2, Q3)
                # Avoid duplicates using (year, quarter) tuple
                if year and quarter and net_income is not None and (year, quarter) not in seen_quarters:
                    quarterly_net_income.append({
                        'year': year,
                        'quarter': quarter,
                        'net_income': net_income,
                        'fiscal_end': fiscal_end
                    })
                    seen_quarters.add((year, quarter))

        # Get annual data to calculate Q4
        annual_net_income = []
        seen_annual_years = set()

        for entry in net_income_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                year = entry.get('fy')
                net_income = entry.get('val')
                fiscal_end = entry.get('end')

                if year and net_income is not None and year not in seen_annual_years:
                    annual_net_income.append({
                        'year': year,
                        'net_income': net_income,
                        'fiscal_end': fiscal_end
                    })
                    seen_annual_years.add(year)

        # EDGAR reports cumulative (year-to-date) Net Income for quarterly filings
        # Q1 = Q1, Q2 = Q1+Q2 cumulative, Q3 = Q1+Q2+Q3 cumulative
        # We need to convert to individual quarters: Q2_actual = Q2_cumulative - Q1, etc.

        annual_by_year = {entry['year']: entry for entry in annual_net_income}

        # Group quarterly data by year
        quarterly_by_year = {}
        for entry in quarterly_net_income:
            year = entry['year']
            if year not in quarterly_by_year:
                quarterly_by_year[year] = []
            quarterly_by_year[year].append(entry)

        # Convert cumulative quarters to individual quarters and calculate Q4
        converted_quarterly = []

        for year, annual_entry in annual_by_year.items():
            if year in quarterly_by_year:
                quarters = quarterly_by_year[year]
                quarters_dict = {q['quarter']: q for q in quarters}

                # Only proceed if we have Q1, Q2, and Q3
                if all(f'Q{i}' in quarters_dict for i in [1, 2, 3]):
                    # Get cumulative values from EDGAR
                    q1_cumulative = quarters_dict['Q1']['net_income']
                    q2_cumulative = quarters_dict['Q2']['net_income']
                    q3_cumulative = quarters_dict['Q3']['net_income']
                    annual_ni = annual_entry['net_income']

                    # Convert to individual quarter values
                    q1_individual = q1_cumulative
                    q2_individual = q2_cumulative - q1_cumulative
                    q3_individual = q3_cumulative - q2_cumulative
                    q4_individual = annual_ni - q3_cumulative

                    # Validate that individual quarters sum to annual (within rounding tolerance)
                    calculated_annual = q1_individual + q2_individual + q3_individual + q4_individual
                    if abs(calculated_annual - annual_ni) < 1000:
                        # Add converted individual quarters
                        converted_quarterly.append({
                            'year': year,
                            'quarter': 'Q1',
                            'net_income': q1_individual,
                            'fiscal_end': quarters_dict['Q1']['fiscal_end']
                        })
                        converted_quarterly.append({
                            'year': year,
                            'quarter': 'Q2',
                            'net_income': q2_individual,
                            'fiscal_end': quarters_dict['Q2']['fiscal_end']
                        })
                        converted_quarterly.append({
                            'year': year,
                            'quarter': 'Q3',
                            'net_income': q3_individual,
                            'fiscal_end': quarters_dict['Q3']['fiscal_end']
                        })
                        converted_quarterly.append({
                            'year': year,
                            'quarter': 'Q4',
                            'net_income': q4_individual,
                            'fiscal_end': annual_entry['fiscal_end']
                        })
                        logger.debug(f"[FY{year}] Individual quarters: Q1=${q1_individual:,.0f}, Q2=${q2_individual:,.0f}, Q3=${q3_individual:,.0f}, Q4=${q4_individual:,.0f} (sum=${calculated_annual:,.0f} vs annual=${annual_ni:,.0f})")
                    else:
                        logger.warning(f"[FY{year}] Inconsistent quarterly data: quarters sum to ${calculated_annual:,.0f} but annual is ${annual_ni:,.0f}. Q1=${q1_individual:,.0f}, Q2=${q2_individual:,.0f}, Q3=${q3_individual:,.0f}, Q4=${q4_individual:,.0f}")

        quarterly_net_income = converted_quarterly

        # Sort by year descending, then by quarter
        def quarter_sort_key(entry):
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            return (-entry['year'], quarter_order.get(entry['quarter'], 0))

        quarterly_net_income.sort(key=quarter_sort_key)

        # Count Q4s
        q4_count = sum(1 for entry in quarterly_net_income if entry['quarter'] == 'Q4')
        logger.info(f"Successfully parsed {len(quarterly_net_income)} quarters of Net Income data from EDGAR ({q4_count} Q4s calculated)")
        return quarterly_net_income

    def parse_shares_outstanding_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract weighted average shares outstanding history (split-adjusted)

        EDGAR reports WeightedAverageNumberOfDilutedSharesOutstanding which is
        already split-adjusted. Combined with Net Income, this allows calculation
        of split-adjusted EPS.

        Supports both US-GAAP (domestic companies) and IFRS (foreign companies).

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, shares, and fiscal_end values
        """
        shares_data_list = None

        # Try US-GAAP first (domestic companies)
        try:
            shares_units = company_facts['facts']['us-gaap']['WeightedAverageNumberOfDilutedSharesOutstanding']['units']
            if 'shares' in shares_units:
                shares_data_list = shares_units['shares']
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS (foreign companies filing 20-F)
        if shares_data_list is None:
            try:
                shares_units = company_facts['facts']['ifrs-full']['WeightedAverageNumberOfSharesOutstandingDiluted']['units']
                if 'shares' in shares_units:
                    shares_data_list = shares_units['shares']
            except (KeyError, TypeError):
                pass

        # If we still don't have data, return empty
        if shares_data_list is None:
            logger.debug("Could not parse shares outstanding history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Filter for annual reports (10-K for US, 20-F for foreign)
        # Use dict to keep only the latest fiscal_end for each year
        annual_shares_by_year = {}

        # Group by fiscal_end first to get all entries for same historical period
        by_fiscal_end = {}

        for entry in shares_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fiscal_end = entry.get('end')
                shares = entry.get('val')
                fy = entry.get('fy')  # Filing year

                if fiscal_end and shares is not None:
                    if fiscal_end not in by_fiscal_end:
                        by_fiscal_end[fiscal_end] = []
                    by_fiscal_end[fiscal_end].append({
                        'fiscal_end': fiscal_end,
                        'shares': shares,
                        'fy': fy
                    })

        # For each fiscal_end, keep the entry from the LATEST filing (highest fy)
        # because later filings have split-adjusted historical data
        for fiscal_end, entries in by_fiscal_end.items():
            # Sort by fy descending to get latest filing first
            entries_sorted = sorted(entries, key=lambda x: x.get('fy') or 0, reverse=True)
            latest_entry = entries_sorted[0]

            # Extract year from fiscal_end date
            year = int(fiscal_end[:4]) if fiscal_end else None

            if year:
                # Keep only the latest fiscal_end for each year (in case of restated periods)
                if year not in annual_shares_by_year or fiscal_end > annual_shares_by_year[year]['fiscal_end']:
                    annual_shares_by_year[year] = {
                        'year': year,
                        'shares': latest_entry['shares'],
                        'fiscal_end': fiscal_end
                    }

        # Convert dict to list and sort by year descending
        annual_shares = list(annual_shares_by_year.values())
        annual_shares.sort(key=lambda x: x['year'], reverse=True)

        # Normalize shares units: EDGAR reports shares in inconsistent units
        # Some companies report in millions (e.g., 721.9) vs actual count (e.g., 721,900,000)
        # This is due to inline XBRL (iXBRL) format adoption around 2021-2022
        # Heuristic: shares < 10,000 are assumed to be in millions
        normalized_count = 0
        for entry in annual_shares:
            shares = entry['shares']
            
            # Detect if shares are in millions (no public company has < 10,000 actual shares)
            if shares < 10_000:
                # Convert millions to actual shares
                original_shares = shares
                entry['shares'] = shares * 1_000_000
                normalized_count += 1
                logger.info(f"Normalized shares for year {entry['year']}: {original_shares:.2f}M -> {entry['shares']:,.0f}")
        
        if normalized_count > 0:
            logger.info(f"Total years normalized from millions to actual: {normalized_count}/{len(annual_shares)}")

        # Detect and apply stock splits to historical data
        # If shares jump significantly (>1.5x) between consecutive years, it's likely a stock split
        # Apply the split ratio backwards to earlier years
        if len(annual_shares) >= 2:
            for i in range(len(annual_shares) - 1):
                current_year = annual_shares[i]
                next_year = annual_shares[i + 1]

                # Calculate ratio between consecutive years
                if next_year['shares'] > 0:
                    ratio = current_year['shares'] / next_year['shares']

                    # If shares increased by >1.5x, likely a stock split
                    if ratio > 1.5:
                        # Determine split ratio (round to common splits: 2, 3, 4, 7, etc)
                        if 1.8 < ratio < 2.2:
                            split_ratio = 2
                        elif 2.8 < ratio < 3.2:
                            split_ratio = 3
                        elif 3.5 < ratio < 4.5:
                            split_ratio = 4
                        elif 6.5 < ratio < 7.5:
                            split_ratio = 7
                        else:
                            # Use actual ratio if it doesn't match common splits
                            split_ratio = ratio

                        logger.info(f"Detected {split_ratio}-for-1 stock split between {next_year['year']} and {current_year['year']}")

                        # Apply split to all earlier years
                        for j in range(i + 1, len(annual_shares)):
                            annual_shares[j]['shares'] *= split_ratio
                            logger.debug(f"Applied {split_ratio}x split adjustment to {annual_shares[j]['year']}")

                        # Break after first split detection to avoid double-adjusting
                        break

        logger.info(f"Successfully parsed {len(annual_shares)} years of shares outstanding data from EDGAR")
        return annual_shares

    def parse_quarterly_shares_outstanding_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract quarterly weighted average shares outstanding (split-adjusted)

        Unlike Net Income, shares outstanding are typically NOT cumulative in quarterly
        filings - each quarter reports the weighted average shares for that specific quarter.

        Supports both US-GAAP (domestic companies) and IFRS (foreign companies).

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter, shares, and fiscal_end values
        """
        shares_data_list = None

        # Try US-GAAP first (domestic companies)
        try:
            shares_units = company_facts['facts']['us-gaap']['WeightedAverageNumberOfDilutedSharesOutstanding']['units']
            if 'shares' in shares_units:
                shares_data_list = shares_units['shares']
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS (foreign companies filing 6-K)
        if shares_data_list is None:
            try:
                shares_units = company_facts['facts']['ifrs-full']['WeightedAverageNumberOfSharesOutstandingDiluted']['units']
                if 'shares' in shares_units:
                    shares_data_list = shares_units['shares']
            except (KeyError, TypeError):
                pass

        # If we still don't have data, return empty
        if shares_data_list is None:
            logger.debug("Could not parse quarterly shares outstanding history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Extract quarterly reports (10-Q for US, 6-K for foreign)
        quarterly_shares = []
        seen_quarters = set()

        for entry in shares_data_list:
            if entry.get('form') in ['10-Q', '6-K']:
                fiscal_end = entry.get('end')
                # Extract year from fiscal_end date (more reliable than fy field)
                year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
                quarter = entry.get('fp')  # Fiscal period: Q1, Q2, Q3
                shares = entry.get('val')

                # Only include entries with fiscal period (Q1, Q2, Q3)
                # Avoid duplicates using (year, quarter) tuple
                if year and quarter and shares is not None and (year, quarter) not in seen_quarters:
                    quarterly_shares.append({
                        'year': year,
                        'quarter': quarter,
                        'shares': shares,
                        'fiscal_end': fiscal_end
                    })
                    seen_quarters.add((year, quarter))

        # Get annual data for Q4
        # Q4 shares are typically reported in the 10-K
        annual_shares = []
        seen_annual_years = set()

        for entry in shares_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fiscal_end = entry.get('end')
                # Use fy field (fiscal year) as primary source, fall back to extracting from fiscal_end date
                year = entry.get('fy') or (int(fiscal_end[:4]) if fiscal_end else None)
                shares = entry.get('val')

                if year and shares is not None and year not in seen_annual_years:
                    annual_shares.append({
                        'year': year,
                        'shares': shares,
                        'fiscal_end': fiscal_end
                    })
                    seen_annual_years.add(year)

        # Add Q4 from annual reports
        annual_by_year = {entry['year']: entry for entry in annual_shares}

        # Normalize shares units for both quarterly and annual data (same heuristic as annual)
        normalized_quarterly = 0
        for entry in quarterly_shares:
            if entry['shares'] < 10_000:
                original = entry['shares']
                entry['shares'] = original * 1_000_000
                normalized_quarterly += 1
                logger.debug(f"Normalized quarterly shares for {entry['year']} {entry['quarter']}: {original:.2f}M -> {entry['shares']:,.0f}")
        
        normalized_annual_q4 = 0
        for entry in annual_shares:
            if entry['shares'] < 10_000:
                original = entry['shares']
                entry['shares'] = original * 1_000_000
                normalized_annual_q4 += 1
                logger.debug(f"Normalized annual Q4 shares for {entry['year']}: {original:.2f}M -> {entry['shares']:,.0f}")
        
        if normalized_quarterly > 0 or normalized_annual_q4 > 0:
            logger.info(f"Quarterly shares normalization: {normalized_quarterly} quarters, {normalized_annual_q4} annual Q4s")

        for year, annual_entry in annual_by_year.items():
            # Add Q4 if we don't already have it from a 10-Q
            if (year, 'Q4') not in seen_quarters:
                quarterly_shares.append({
                    'year': year,
                    'quarter': 'Q4',
                    'shares': annual_entry['shares'],
                    'fiscal_end': annual_entry['fiscal_end']
                })

        # Sort by year descending, then by quarter
        def quarter_sort_key(entry):
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            return (-entry['year'], quarter_order.get(entry['quarter'], 0))

        quarterly_shares.sort(key=quarter_sort_key)
        logger.info(f"Successfully parsed {len(quarterly_shares)} quarters of shares outstanding data from EDGAR")
        return quarterly_shares

    def calculate_split_adjusted_annual_eps_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate split-adjusted annual EPS from Net Income and shares outstanding

        This combines split-independent Net Income with split-adjusted weighted average
        shares outstanding to produce accurate EPS values that remain consistent across
        stock split events.

        Formula: EPS = Net Income / Weighted Average Shares Outstanding

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, eps, net_income, shares, and fiscal_end values
        """
        # Get Net Income (split-independent)
        net_income_annual = self.parse_net_income_history(company_facts)

        # Get shares outstanding (split-adjusted)
        shares_annual = self.parse_shares_outstanding_history(company_facts)

        # Create lookup dict for shares by year
        # Note: Now that we extract year from fiscal_end consistently, years should match
        shares_by_year = {entry['year']: entry for entry in shares_annual}

        # Calculate EPS for each year
        eps_history = []
        for ni_entry in net_income_annual:
            year = ni_entry['year']
            fiscal_end = ni_entry['fiscal_end']

            if year in shares_by_year:
                net_income = ni_entry['net_income']
                shares = shares_by_year[year]['shares']

                if shares > 0:
                    eps = net_income / shares
                    eps_history.append({
                        'year': year,
                        'eps': eps,
                        'net_income': net_income,
                        'shares': shares,
                        'fiscal_end': fiscal_end
                    })

        # Sort by year descending
        eps_history.sort(key=lambda x: x['year'], reverse=True)
        logger.info(f"Successfully calculated {len(eps_history)} years of split-adjusted EPS")
        return eps_history

    def calculate_split_adjusted_quarterly_eps_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate split-adjusted quarterly EPS from Net Income and shares outstanding

        This combines split-independent quarterly Net Income with split-adjusted weighted
        average shares outstanding to produce accurate quarterly EPS values.

        Formula: EPS = Net Income / Weighted Average Shares Outstanding

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter, eps, net_income, shares, and fiscal_end values
        """
        # Get quarterly Net Income (individual quarters, not cumulative)
        net_income_quarterly = self.parse_quarterly_net_income_history(company_facts)

        # Get quarterly shares outstanding
        shares_quarterly = self.parse_quarterly_shares_outstanding_history(company_facts)

        # Create lookup dict for shares by (year, quarter)
        shares_by_quarter = {(entry['year'], entry['quarter']): entry for entry in shares_quarterly}

        # Calculate EPS for each quarter
        eps_history = []
        for ni_entry in net_income_quarterly:
            year = ni_entry['year']
            quarter = ni_entry['quarter']
            key = (year, quarter)

            if key in shares_by_quarter:
                net_income = ni_entry['net_income']
                shares = shares_by_quarter[key]['shares']

                if shares > 0:
                    eps = net_income / shares
                    eps_history.append({
                        'year': year,
                        'quarter': quarter,
                        'eps': eps,
                        'net_income': net_income,
                        'shares': shares,
                        'fiscal_end': ni_entry['fiscal_end']
                    })

        # Sort by year descending, then by quarter
        def quarter_sort_key(entry):
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            return (-entry['year'], quarter_order.get(entry['quarter'], 0))

        eps_history.sort(key=quarter_sort_key)
        logger.info(f"Successfully calculated {len(eps_history)} quarters of split-adjusted EPS")
        return eps_history

    def parse_revenue_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract revenue history from company facts (supports both US-GAAP and IFRS)

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, revenue, and fiscal_end values
        """
        # Use dict to keep only the latest fiscal_end for each year
        annual_revenue_by_year = {}
        fields_found = []

        # Try US-GAAP first (domestic companies)
        try:
            # Try multiple possible field names for revenue
            # Companies often change field names over time, so we collect from ALL fields
            revenue_fields = [
                'Revenues',
                'RevenueFromContractWithCustomerExcludingAssessedTax',
                'SalesRevenueNet',
                'RevenueFromContractWithCustomerIncludingAssessedTax',
                'SalesRevenueGoodsNet',
                'SalesRevenueServicesNet',
                'RevenuesNetOfInterestExpense',
                'RegulatedAndUnregulatedOperatingRevenue',
                'HealthCareOrganizationRevenue',
                'InterestAndDividendIncomeOperating'
            ]

            for field in revenue_fields:
                try:
                    revenue_data = company_facts['facts']['us-gaap'][field]['units']['USD']
                    fields_found.append(field)
                    logger.info(f"Found revenue data using field: '{field}'")

                    # Filter for 10-K annual reports
                    for entry in revenue_data:
                        if entry.get('form') == '10-K':
                            fiscal_end = entry.get('end')
                            frame = entry.get('frame', '')
                            revenue = entry.get('val')

                            # Skip quarterly entries (frames ending in Q1, Q2, Q3, Q4)
                            if frame and frame.endswith(('Q1', 'Q2', 'Q3', 'Q4')):
                                continue

                            if revenue and fiscal_end:
                                # Use fiscal_end year as the key (this is the actual fiscal year)
                                year = int(fiscal_end[:4])

                                # Group by unique fiscal_end dates, keep highest revenue
                                if fiscal_end not in annual_revenue_by_year:
                                    annual_revenue_by_year[fiscal_end] = {
                                        'year': year,
                                        'revenue': revenue,
                                        'fiscal_end': fiscal_end
                                    }
                                elif revenue > annual_revenue_by_year[fiscal_end]['revenue']:
                                    # Keep highest value (in case of duplicates)
                                    annual_revenue_by_year[fiscal_end] = {
                                        'year': year,
                                        'revenue': revenue,
                                        'fiscal_end': fiscal_end
                                    }

                except KeyError:
                    logger.debug(f"Revenue field '{field}' not found, trying next...")
                    continue

        except (KeyError, TypeError):
            pass

        # Fall back to IFRS if no US-GAAP data found (foreign companies filing 20-F)
        if not annual_revenue_by_year:
            try:
                ifrs_revenue_fields = ['Revenue', 'RevenueFromSaleOfGoods']

                for field in ifrs_revenue_fields:
                    try:
                        revenue_units = company_facts['facts']['ifrs-full'][field]['units']

                        # Prefer USD if available, otherwise use any currency
                        revenue_data = None
                        if 'USD' in revenue_units:
                            revenue_data = revenue_units['USD']
                        else:
                            # Find first currency unit (3-letter code)
                            currency_units = [u for u in revenue_units.keys() if len(u) == 3 and u.isupper()]
                            if currency_units:
                                revenue_data = revenue_units[currency_units[0]]

                        if revenue_data:
                            fields_found.append(f"ifrs-full:{field}")
                            logger.info(f"Found IFRS revenue data using field: '{field}'")

                            # Filter for 20-F annual reports
                            for entry in revenue_data:
                                if entry.get('form') == '20-F':
                                    fiscal_end = entry.get('end')
                                    frame = entry.get('frame', '')
                                    revenue = entry.get('val')

                                    # Skip quarterly entries (frames ending in Q1, Q2, Q3, Q4)
                                    if frame and frame.endswith(('Q1', 'Q2', 'Q3', 'Q4')):
                                        continue

                                    if revenue and fiscal_end:
                                        # Use fiscal_end year as the key (this is the actual fiscal year)
                                        year = int(fiscal_end[:4])

                                        # Group by unique fiscal_end dates, keep highest revenue
                                        if fiscal_end not in annual_revenue_by_year:
                                            annual_revenue_by_year[fiscal_end] = {
                                                'year': year,
                                                'revenue': revenue,
                                                'fiscal_end': fiscal_end
                                            }
                                        elif revenue > annual_revenue_by_year[fiscal_end]['revenue']:
                                            # Keep highest value (in case of duplicates)
                                            annual_revenue_by_year[fiscal_end] = {
                                                'year': year,
                                                'revenue': revenue,
                                                'fiscal_end': fiscal_end
                                            }

                    except KeyError:
                        logger.debug(f"IFRS revenue field '{field}' not found, trying next...")
                        continue

            except (KeyError, TypeError):
                pass

        if not annual_revenue_by_year:
            logger.debug(f"No revenue data found in us-gaap or ifrs-full")
            return []

        # Group by year, keeping highest revenue per year
        # (This handles cases where multiple fiscal_end dates map to same year)
        by_year = {}
        for fiscal_end, entry in annual_revenue_by_year.items():
            year = entry['year']
            if year not in by_year:
                by_year[year] = entry
            elif entry['revenue'] > by_year[year]['revenue']:
                by_year[year] = entry

        # Convert dict to list and sort by year descending
        annual_revenue = list(by_year.values())
        annual_revenue.sort(key=lambda x: x['year'], reverse=True)
        logger.info(f"Successfully parsed {len(annual_revenue)} years of revenue data from {len(fields_found)} field(s): {', '.join(fields_found)}")
        return annual_revenue

    def parse_debt_to_equity(self, company_facts: Dict[str, Any]) -> Optional[float]:
        """
        Calculate debt-to-equity ratio from company facts

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            Debt-to-equity ratio or None if data unavailable
        """
        try:
            facts = company_facts['facts']['us-gaap']

            # Get most recent equity value
            equity_data = facts.get('StockholdersEquity', {}).get('units', {}).get('USD', [])
            if not equity_data:
                return None

            # Find most recent 10-K entry
            equity_entries = [e for e in equity_data if e.get('form') == '10-K']
            if not equity_entries:
                return None

            equity_entries.sort(key=lambda x: x.get('end', ''), reverse=True)
            equity = equity_entries[0].get('val')
            fiscal_end = equity_entries[0].get('end', '')

            # Get total debt (long-term + short-term)
            # LongTermDebtNoncurrent = long-term debt
            long_term_debt_data = facts.get('LongTermDebtNoncurrent', {}).get('units', {}).get('USD', [])
            if not long_term_debt_data:
                # Fallback: try LongTermDebt which might include both
                long_term_debt_data = facts.get('LongTermDebt', {}).get('units', {}).get('USD', [])

            # LongTermDebtCurrent = current portion of long-term debt (short-term)
            short_term_debt_data = facts.get('LongTermDebtCurrent', {}).get('units', {}).get('USD', [])

            # Get values matching the same fiscal period as equity
            long_term_debt = None
            if long_term_debt_data:
                matching_entries = [e for e in long_term_debt_data if e.get('form') == '10-K' and e.get('end', '') == fiscal_end]
                if matching_entries:
                    long_term_debt = matching_entries[0].get('val', 0)

            short_term_debt = None
            if short_term_debt_data:
                matching_entries = [e for e in short_term_debt_data if e.get('form') == '10-K' and e.get('end', '') == fiscal_end]
                if matching_entries:
                    short_term_debt = matching_entries[0].get('val', 0)

            # Calculate total debt
            total_debt = 0
            if long_term_debt is not None:
                total_debt += long_term_debt
            if short_term_debt is not None:
                total_debt += short_term_debt

            # Only calculate D/E if we have both debt and equity
            if equity and equity > 0 and (long_term_debt is not None or short_term_debt is not None):
                return total_debt / equity

            return None

        except (KeyError, TypeError):
            return None

    def parse_debt_to_equity_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract historical debt-to-equity ratios from company facts

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, debt_to_equity, and fiscal_end values
        """
        try:
            facts = company_facts['facts']['us-gaap']

            # Get equity data - try multiple tags in order of preference
            equity_tags = [
                'StockholdersEquity',
                'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
                'CommonStockholdersEquity',
                'LiabilitiesAndStockholdersEquity'  # Last resort - total assets
            ]

            equity_data = []
            for tag in equity_tags:
                equity_data = facts.get(tag, {}).get('units', {}).get('USD', [])
                if equity_data:
                    logger.debug(f"Using equity tag: {tag}")
                    break

            if not equity_data:
                logger.debug("No equity data found in EDGAR")
                return []

            # Get debt data - merge multiple fields to avoid gaps
            # Use a prioritized list of tags commonly used for Debt
            # Aggregate tags first, followed by specific instrument types
            lt_debt_tags = [
                'LongTermDebtNoncurrent', 
                'LongTermDebt',
                'SeniorLongTermNotes',
                'ConvertibleDebt',
                'ConvertibleLongTermNotesPayable',
                'NotesPayable',
                'LongTermNotesPayable',
                'DebtInstrumentCarryingAmount',
                'LongTermDebtAndCapitalLeaseObligations',
                'CapitalLeaseObligationsNoncurrent',
                'OtherLongTermDebtNoncurrent'
            ]
            
            long_term_debt_data = []
            for tag in lt_debt_tags:
                data = facts.get(tag, {}).get('units', {}).get('USD', [])
                if data:
                    long_term_debt_data.extend(data)

            # Get short-term debt data from multiple sources
            st_debt_tags = [
                'LongTermDebtCurrent',
                'DebtCurrent',
                'NotesPayableCurrent',
                'ConvertibleNotesPayableCurrent',
                'ShortTermBorrowings',
                'CommercialPaper',
                'LinesOfCreditCurrent',
                'CapitalLeaseObligationsCurrent',
                'OtherLongTermDebtCurrent'
            ]
            
            short_term_debt_data = []
            for tag in st_debt_tags:
                data = facts.get(tag, {}).get('units', {}).get('USD', [])
                if data:
                    short_term_debt_data.extend(data)

            # Filter for 10-K entries and create lookup by fiscal year and end date
            equity_by_year = {}
            for entry in equity_data:
                if entry.get('form') == '10-K':
                    year = entry.get('fy')
                    fiscal_end = entry.get('end')
                    val = entry.get('val')
                    if year and val and year not in equity_by_year:
                        equity_by_year[year] = {'val': val, 'fiscal_end': fiscal_end}

            # Build long-term debt by year (first entry per year wins)
            long_term_debt_by_year = {}
            if long_term_debt_data:
                for entry in long_term_debt_data:
                    if entry.get('form') == '10-K':
                        year = entry.get('fy')
                        fiscal_end = entry.get('end')
                        val = entry.get('val')
                        if year and val is not None and year not in long_term_debt_by_year:
                            long_term_debt_by_year[year] = {'val': val, 'fiscal_end': fiscal_end}

            # Build short-term debt by year
            short_term_debt_by_year = {}
            if short_term_debt_data:
                for entry in short_term_debt_data:
                    if entry.get('form') == '10-K':
                        year = entry.get('fy')
                        fiscal_end = entry.get('end')
                        val = entry.get('val')
                        if year and val is not None and year not in short_term_debt_by_year:
                            short_term_debt_by_year[year] = {'val': val, 'fiscal_end': fiscal_end}

            # Calculate D/E ratio for each year where we have equity and at least one debt component
            debt_to_equity_history = []
            for year in equity_by_year.keys():
                equity = equity_by_year[year]['val']
                fiscal_end = equity_by_year[year]['fiscal_end']

                # Calculate total debt for this year
                total_debt = 0
                has_debt_data = False

                if year in long_term_debt_by_year:
                    total_debt += long_term_debt_by_year[year]['val']
                    has_debt_data = True

                if year in short_term_debt_by_year:
                    total_debt += short_term_debt_by_year[year]['val']
                    has_debt_data = True

                # Only calculate D/E if we have both equity and some debt data
                # Allow negative equity (deficit) which results in negative D/E ratio
                if equity != 0 and has_debt_data:
                    debt_to_equity = total_debt / equity
                    debt_to_equity_history.append({
                        'year': year,
                        'debt_to_equity': debt_to_equity,
                        'fiscal_end': fiscal_end
                    })

            # Sort by year descending
            debt_to_equity_history.sort(key=lambda x: x['year'], reverse=True)
            logger.info(f"Successfully parsed {len(debt_to_equity_history)} years of D/E ratio data from EDGAR")
            return debt_to_equity_history

        except (KeyError, TypeError) as e:
            logger.warning(f"Error parsing D/E history: {e}")
            return []

    def fetch_stock_fundamentals(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch complete fundamental data for a stock

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with eps_history, revenue_history, and debt_to_equity
        """
        # Get CIK for ticker
        cik = self.get_cik_for_ticker(ticker)
        if not cik:
            return None

        # Fetch company facts
        company_facts = self.fetch_company_facts(cik)
        if not company_facts:
            return None

        # Parse all fundamental data
        eps_history = self.parse_eps_history(company_facts)
        revenue_history = self.parse_revenue_history(company_facts)
        debt_to_equity = self.parse_debt_to_equity(company_facts)
        debt_to_equity_history = self.parse_debt_to_equity_history(company_facts)
        cash_flow_history = self.parse_cash_flow_history(company_facts)

        # Calculate split-adjusted EPS from Net Income / Shares Outstanding
        calculated_eps_history = self.calculate_split_adjusted_annual_eps_history(company_facts)

        # Extract Net Income directly for storage
        net_income_annual = self.parse_net_income_history(company_facts)
        net_income_quarterly = self.parse_quarterly_net_income_history(company_facts)
        
        # Parse dividend history
        dividend_history = self.parse_dividend_history(company_facts)

        logger.info(f"[{ticker}] EDGAR fetch complete: {len(eps_history)} EPS years, {len(calculated_eps_history)} calculated EPS years, {len(net_income_annual)} annual NI, {len(net_income_quarterly)} quarterly NI, {len(revenue_history)} revenue years, {len(debt_to_equity_history)} D/E years, {len(cash_flow_history)} cash flow years, {len(dividend_history)} dividend entries, current D/E: {debt_to_equity}")

        fundamentals = {
            'ticker': ticker,
            'cik': cik,
            'company_name': company_facts.get('entityName', ''),
            'eps_history': eps_history,
            'calculated_eps_history': calculated_eps_history,
            'net_income_annual': net_income_annual,
            'net_income_quarterly': net_income_quarterly,
            'revenue_history': revenue_history,
            'debt_to_equity': debt_to_equity,
            'debt_to_equity_history': debt_to_equity_history,
            'cash_flow_history': cash_flow_history,
            'dividend_history': dividend_history,
            'company_facts': company_facts
        }

        return fundamentals

    def fetch_recent_filings(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Fetch recent 10-K and 10-Q filings for a ticker

        Returns:
            List of filing dicts with 'type', 'date', 'url', 'accession_number'
        """
        cik = self.get_cik_for_ticker(ticker)
        if not cik:
            logger.warning(f"[{ticker}] Could not find CIK")
            return []

        # Pad CIK to 10 digits
        padded_cik = cik.zfill(10)

        try:
            self._rate_limit()
            submissions_url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
            response = requests.get(submissions_url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            recent_filings = data.get('filings', {}).get('recent', {})

            if not recent_filings:
                logger.warning(f"[{ticker}] No recent filings found")
                return []

            forms = recent_filings.get('form', [])
            filing_dates = recent_filings.get('filingDate', [])
            accession_numbers = recent_filings.get('accessionNumber', [])
            primary_documents = recent_filings.get('primaryDocument', [])

            filings = []
            for i, form in enumerate(forms):
                if form in ['10-K', '10-Q']:
                    # Remove dashes from accession number for URL
                    acc_num = accession_numbers[i]
                    acc_num_no_dashes = acc_num.replace('-', '')
                    primary_doc = primary_documents[i] if i < len(primary_documents) else None

                    # Build the raw filing HTML URL
                    # Format: https://www.sec.gov/Archives/edgar/data/{CIK}/{ACCESSION_NO_DASHES}/{PRIMARY_DOC}
                    if primary_doc:
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_no_dashes}/{primary_doc}"
                    else:
                        # Fallback: try common filing name pattern
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_no_dashes}/{acc_num_no_dashes}.txt"

                    filings.append({
                        'type': form,
                        'date': filing_dates[i],
                        'url': doc_url,
                        'accession_number': acc_num
                    })

            logger.info(f"[SECDataFetcher][{ticker}] Found {len(filings)} 10-K/10-Q filings")
            return filings

        except Exception as e:
            logger.error(f"[{ticker}] Error fetching filings: {e}")
            return []

    def extract_filing_sections(self, ticker: str, filing_type: str) -> Dict[str, Any]:
        """
        Extract key sections from a SEC filing using edgartools

        Args:
            ticker: Stock ticker symbol
            filing_type: '10-K' or '10-Q'

        Returns:
            Dictionary with extracted sections:
                - business: Item 1 (10-K only)
                - risk_factors: Item 1A (10-K only)
                - mda: Item 7 (10-K) or Item 2 (10-Q)
                - market_risk: Item 7A (10-K) or Item 3 (10-Q)
        """
        logger.info(f"[SECDataFetcher][{ticker}] Extracting sections from {filing_type} using edgartools")
        sections = {}

        try:
            # Get CIK first to avoid edgartools ticker lookup issues
            cik = self.get_cik_for_ticker(ticker)
            if not cik:
                logger.warning(f"[SECDataFetcher][{ticker}] Could not find CIK for section extraction")
                return {}

            # Get company using cached Company object (avoids redundant SEC calls)
            company = self.get_company(cik)
            if not company:
                logger.warning(f"[SECDataFetcher][{ticker}] Could not get Company object")
                return {}
            filings = company.get_filings(form=filing_type)

            if not filings:
                logger.warning(f"[SECDataFetcher][{ticker}] No {filing_type} filings found")
                return {}

            latest_filing = filings.latest()
            filing_date = str(latest_filing.filing_date)
            logger.info(f"[SECDataFetcher][{ticker}] Found {filing_type} filing from {filing_date}")

            # Get the structured filing object
            filing_obj = latest_filing.obj()

            if filing_type == '10-K':
                # Extract 10-K sections
                if hasattr(filing_obj, 'business') and filing_obj.business:
                    sections['business'] = {
                        'content': filing_obj.business,
                        'filing_type': '10-K',
                        'filing_date': filing_date
                    }
                    logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 1 (Business): {len(filing_obj.business)} chars")

                if hasattr(filing_obj, 'risk_factors') and filing_obj.risk_factors:
                    sections['risk_factors'] = {
                        'content': filing_obj.risk_factors,
                        'filing_type': '10-K',
                        'filing_date': filing_date
                    }
                    logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 1A (Risk Factors): {len(filing_obj.risk_factors)} chars")

                if hasattr(filing_obj, 'management_discussion') and filing_obj.management_discussion:
                    sections['mda'] = {
                        'content': filing_obj.management_discussion,
                        'filing_type': '10-K',
                        'filing_date': filing_date
                    }
                    logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 7 (MD&A): {len(filing_obj.management_discussion)} chars")

                # Try to get Item 7A (Market Risk) via bracket notation
                try:
                    market_risk = filing_obj["Item 7A"]
                    if market_risk:
                        sections['market_risk'] = {
                            'content': market_risk,
                            'filing_type': '10-K',
                            'filing_date': filing_date
                        }
                        logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 7A (Market Risk): {len(market_risk)} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[SECDataFetcher][{ticker}] Item 7A (Market Risk) not available")

            elif filing_type == '10-Q':
                # Extract 10-Q sections via bracket notation
                try:
                    mda = filing_obj["Item 2"]
                    if mda:
                        sections['mda'] = {
                            'content': mda,
                            'filing_type': '10-Q',
                            'filing_date': filing_date
                        }
                        logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 2 (MD&A): {len(str(mda))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[SECDataFetcher][{ticker}] Item 2 (MD&A) not available in 10-Q")

                try:
                    market_risk = filing_obj["Item 3"]
                    if market_risk:
                        sections['market_risk'] = {
                            'content': market_risk,
                            'filing_type': '10-Q',
                            'filing_date': filing_date
                        }
                        logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 3 (Market Risk): {len(str(market_risk))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[SECDataFetcher][{ticker}] Item 3 (Market Risk) not available in 10-Q")

            logger.info(f"[SECDataFetcher][{ticker}] Successfully extracted {len(sections)} sections from {filing_type}")
            return sections

        except Exception as e:
            logger.error(f"[SECDataFetcher][{ticker}] Error extracting {filing_type} sections: {e}")
            import traceback
            traceback.print_exc()
            return {}
    def parse_dividend_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract dividend history from company facts

        Prioritizes CommonStockDividendsPerShareCashPaid, falls back to CommonStockDividendsPerShareDeclared.
        Supports both US-GAAP and IFRS.

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter (optional), amount, and fiscal_end values
        """
        # Merge data from all available dividend tags
        all_dividend_data = []

        # US-GAAP tags to try
        us_gaap_keys = [
            'CommonStockDividendsPerShareCashPaid',
            'CommonStockDividendsPerShareDeclared',
            'DividendsPayableAmountPerShare'
        ]

        # Try US-GAAP - collect from ALL available tags
        try:
            us_gaap = company_facts['facts']['us-gaap']
            for key in us_gaap_keys:
                if key in us_gaap:
                    units = us_gaap[key]['units']
                    if 'USD/shares' in units:
                        all_dividend_data.extend(units['USD/shares'])
                        logger.debug(f"Found dividend data using US-GAAP key: {key}")
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS if no US-GAAP data found
        if not all_dividend_data:
            try:
                ifrs = company_facts['facts']['ifrs-full']
                ifrs_keys = [
                    'DividendsRecognisedAsDistributionsToOwnersPerShare',
                    'DividendsProposedOrDeclaredBeforeFinancialStatementsAuthorisedForIssuePerShare'
                ]
                for key in ifrs_keys:
                    if key in ifrs:
                        units = ifrs[key]['units']
                        # Find USD/shares or similar
                        for unit_name, entries in units.items():
                            if 'shares' in unit_name:
                                all_dividend_data.extend(entries)
                                logger.debug(f"Found dividend data using IFRS key: {key}")
                                break
            except (KeyError, TypeError):
                pass

        if not all_dividend_data:
            logger.debug("Could not parse dividend history from EDGAR")
            return []

        # Build dictionary to deduplicate and keep best entry for each (year, period, quarter)
        dividends_dict = {}

        for entry in all_dividend_data:
            fiscal_end = entry.get('end')
            # Extract year from fiscal_end date
            year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
            form = entry.get('form')
            amount = entry.get('val')
            filed = entry.get('filed')

            if not year or amount is None:
                continue

            # Determine period
            period = 'annual'
            quarter = None

            if form in ['10-Q', '6-K']:
                fp = entry.get('fp')
                if fp in ['Q1', 'Q2', 'Q3']:
                    period = 'quarterly'
                    quarter = fp
            elif form in ['10-K', '20-F']:
                period = 'annual'

            # Create a unique key to avoid duplicates
            entry_key = (year, period, quarter)

            # Keep the entry with the latest filed date for each key
            if entry_key not in dividends_dict:
                dividends_dict[entry_key] = {
                    'year': year,
                    'period': period,
                    'quarter': quarter,
                    'amount': amount,
                    'fiscal_end': fiscal_end,
                    'filed': filed
                }
            else:
                # If we already have this entry, keep the one with latest filed date
                existing = dividends_dict[entry_key]
                if filed and existing.get('filed'):
                    if filed > existing['filed']:
                        dividends_dict[entry_key] = {
                            'year': year,
                            'period': period,
                            'quarter': quarter,
                            'amount': amount,
                            'fiscal_end': fiscal_end,
                            'filed': filed
                        }

        dividends = list(dividends_dict.values())

        # Sort by year descending
        dividends.sort(key=lambda x: x['year'], reverse=True)
        
        logger.info(f"Successfully parsed {len(dividends)} dividend entries from EDGAR")
        return dividends
