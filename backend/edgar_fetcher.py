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

        # Filter for quarterly reports (10-Q for US, 6-K for foreign) AND Annual (10-K) to derive Q4
        quarterly_eps = []
        annual_eps_map = {} # Year -> {val, end}
        seen_quarters = set()
        
        from datetime import datetime

        # Sort by end date descending to process most recent filings first
        # This handles cases where EDGAR has duplicate/corrected entries or shifted FY labels
        eps_data_list.sort(key=lambda x: x.get('end', ''), reverse=True)

        for entry in eps_data_list:
            form = entry.get('form')
            if form in ['10-Q', '6-K', '10-K', '20-F', '40-F']:
                fiscal_end = entry.get('end')
                start_date = entry.get('start')
                
                # Use fiscal year from EDGAR's fy field (not calendar year from fiscal_end)
                # This ensures quarterly data matches annual data by fiscal year, not calendar year
                # Critical for companies with non-calendar fiscal years (Apple, Microsoft, etc.)
                year = entry.get('fy')
                if not year:
                    continue

                fp = entry.get('fp')  # Fiscal period: Q1, Q2, Q3, FY, Q4
                val = entry.get('val')
                
                if val is None:
                    continue

                # Determine period type (Annual vs Quarterly)
                is_annual = False
                is_quarterly = False
                
                # Check by FP
                if fp in ['Q1', 'Q2', 'Q3', 'Q4']:
                    is_quarterly = True
                    quarter = fp
                elif fp == 'FY':
                    is_annual = True
                
                # Check by duration if ambiguous (often 10-K has missing FP for Q4/FY)
                if not is_annual and not is_quarterly and start_date and fiscal_end:
                    try:
                        d1 = datetime.strptime(start_date, '%Y-%m-%d')
                        d2 = datetime.strptime(fiscal_end, '%Y-%m-%d')
                        duration = (d2 - d1).days
                        
                        if 350 <= duration <= 375:
                            is_annual = True
                        elif 80 <= duration <= 100:
                            is_quarterly = True
                            # Infer quarter? 
                            # If end date is ~Dec 31 (for cal year), might be Q4?
                            # Without explicit FP, assigning Q1-Q3 is risky, but Q4 is last.
                            # We'll rely on Subtraction fallback for Q4 mostly, 
                            # but if we find explicit Q4 via date matching (aligned with FY end), likely Q4.
                            # Let's verify fiscal year end alignment.
                            # For now, rely on logic: if it's 10-K and ~90 days, it's Q4.
                            if form in ['10-K', '20-F', '40-F']:
                                quarter = 'Q4'
                            else:
                                continue # ambiguous 10-Q date range without fp? skip
                    except:
                        pass

                # Store Data
                if is_annual:
                    # Keep latest (restatements)
                    if year not in annual_eps_map:
                         annual_eps_map[year] = {'val': val, 'end': fiscal_end}
                    else:
                         # Overwrite if fiscal_end is later (correction)
                         if fiscal_end > annual_eps_map[year]['end']:
                             annual_eps_map[year] = {'val': val, 'end': fiscal_end}

                elif is_quarterly and quarter:
                    if (year, quarter) not in seen_quarters:
                        quarterly_eps.append({
                            'year': year,
                            'quarter': quarter,
                            'eps': val,
                            'fiscal_end': fiscal_end
                        })
                        seen_quarters.add((year, quarter))

        # EDGAR reports cumulative (year-to-date) EPS for quarterly filings
        # Q1 = Q1, Q2 = Q1+Q2 cumulative, Q3 = Q1+Q2+Q3 cumulative
        # We need to convert to individual quarters: Q2_actual = Q2_cumulative - Q1, etc.

        annual_by_year = {year: data for year, data in annual_eps_map.items()}

        # Group quarterly data by year
        quarterly_by_year = {}
        for entry in quarterly_eps:
            year = entry['year']
            if year not in quarterly_by_year:
                quarterly_by_year[year] = []
            quarterly_by_year[year].append(entry)

        # Convert cumulative quarters to individual quarters
        # We process all years where we have quarterly data
        converted_quarterly = []
        
        all_years = set(quarterly_by_year.keys())
        
        for year in sorted(all_years, reverse=True):
            quarters_dict = {q['quarter']: q for q in quarterly_by_year.get(year, [])}
            annual_entry = annual_by_year.get(year)
            
            # Q1
            if 'Q1' in quarters_dict:
                q1_cumulative = quarters_dict['Q1']['eps']
                converted_quarterly.append({
                    'year': year,
                    'quarter': 'Q1',
                    'eps': q1_cumulative,
                    'fiscal_end': quarters_dict['Q1']['fiscal_end']
                })
                
                # Q2 (Needs Q1)
                if 'Q2' in quarters_dict:
                    q2_cumulative = quarters_dict['Q2']['eps']
                    q2_individual = q2_cumulative - q1_cumulative
                    converted_quarterly.append({
                        'year': year,
                        'quarter': 'Q2',
                        'eps': q2_individual,
                        'fiscal_end': quarters_dict['Q2']['fiscal_end']
                    })
                    
                    # Q3 (Needs Q2)
                    if 'Q3' in quarters_dict:
                        q3_cumulative = quarters_dict['Q3']['eps']
                        q3_individual = q3_cumulative - q2_cumulative
                        converted_quarterly.append({
                            'year': year,
                            'quarter': 'Q3',
                            'eps': q3_individual,
                            'fiscal_end': quarters_dict['Q3']['fiscal_end']
                        })
                        
                        # Q4 (Needs Annual + Q3)
                        if annual_entry:
                            annual_eps = annual_entry['val']
                            q4_individual = annual_eps - q3_cumulative
                            
                            # Validate sum
                            calculated_annual = q1_cumulative + q2_individual + q3_individual + q4_individual
                            
                            # Add Q4 regardless of minor validation error, but log warning if large
                            if abs(calculated_annual - annual_eps) > 0.5:
                                logger.warning(f"[FY{year}] Q4 calc mismatch: sum={calculated_annual} vs annual={annual_eps}")
                                
                            converted_quarterly.append({
                                'year': year,
                                'quarter': 'Q4',
                                'eps': q4_individual,
                                'fiscal_end': annual_entry['end'],
                                'is_calculated': True
                            })

        quarterly_eps = converted_quarterly

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
        # EDGAR has multiple entries per fiscal year:
        # - Annual values with ~365 day duration (start to end)
        # - Quarterly values with ~90 day duration
        # We filter by duration >= 360 days to ensure we get the annual value.
        # This was validated against SEC filings for AAPL, MSFT, Loews, PG.
        annual_net_income_by_year = {}

        for entry in net_income_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fiscal_end = entry.get('end')
                net_income = entry.get('val')
                start = entry.get('start')

                if net_income is not None and fiscal_end and start:
                    # Calculate period duration - only accept annual periods (≥360 days)
                    try:
                        from datetime import datetime
                        d1 = datetime.strptime(start, '%Y-%m-%d')
                        d2 = datetime.strptime(fiscal_end, '%Y-%m-%d')
                        duration = (d2 - d1).days
                        if duration < 360:
                            continue  # Skip quarterly values
                    except (ValueError, TypeError):
                        continue  # Skip if dates can't be parsed

                    # Use fiscal_end year as the key (this is the actual fiscal year)
                    year = int(fiscal_end[:4])

                    # Keep entry for each unique fiscal_end, preferring later entries 
                    # (which may be restated/corrected values)
                    if fiscal_end not in annual_net_income_by_year:
                        annual_net_income_by_year[fiscal_end] = {
                            'year': year,
                            'net_income': net_income,
                            'fiscal_end': fiscal_end
                        }

        # Group by year (e.g., if fiscal_end is 2024-06-30, that's FY2024)
        by_year = {}
        for fiscal_end, entry in annual_net_income_by_year.items():
            year = entry['year']
            if year not in by_year:
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
                
                # Alternative tag for Banks (MS)
                if 'PaymentsForProceedsFromProductiveAssets' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['PaymentsForProceedsFromProductiveAssets']['units']
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
        # Try US-GAAP first (domestic companies)
        try:
            ni_tags = [
                'NetIncomeLoss',
                'NetIncomeLossAvailableToCommonStockholdersBasic',
                'ProfitLoss',
                'NetIncomeLossAvailableToCommonStockholdersDiluted'
            ]
            
            for tag in ni_tags:
                if tag in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap'][tag]['units']
                    if 'USD' in units:
                        net_income_data_list = units['USD']
                        logger.debug(f"Found Net Income data using tag: {tag}")
                        break
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

        # Sort by end date descending to process most recent filings first
        net_income_data_list.sort(key=lambda x: x.get('end', ''), reverse=True)

        for entry in net_income_data_list:
            if entry.get('form') in ['10-Q', '6-K']:
                fiscal_end = entry.get('end')
                # Use fiscal year from EDGAR's fy field (not calendar year from fiscal_end)
                # This ensures quarterly data matches annual data by fiscal year, not calendar year
                year = entry.get('fy')
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
        # EDGAR has multiple entries per fiscal year:
        # - Annual values with ~365 day duration (start to end)
        # - Quarterly values with ~90 day duration
        # We filter by duration >= 360 days to ensure we get the annual value.
        # This was validated against SEC filings for AAPL, MSFT, Loews, PG.
        annual_net_income_by_year = {}

        for entry in net_income_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fy = entry.get('fy')
                net_income = entry.get('val')
                fiscal_end = entry.get('end')
                start = entry.get('start')

                if fy and net_income is not None and fiscal_end and start:
                    # Calculate period duration - only accept annual periods (≥360 days)
                    try:
                        from datetime import datetime
                        d1 = datetime.strptime(start, '%Y-%m-%d')
                        d2 = datetime.strptime(fiscal_end, '%Y-%m-%d')
                        duration = (d2 - d1).days
                        if duration < 360:
                            continue  # Skip quarterly values
                    except (ValueError, TypeError):
                        continue  # Skip if dates can't be parsed

                    # Extract year from fiscal_end
                    end_year = int(fiscal_end[:4])
                    
                    # Prefer the entry where fiscal_end year matches the fiscal year
                    # This ensures Q4's fiscal_end is correct (e.g., FY2024 -> end=2024-06-30)
                    if fy not in annual_net_income_by_year:
                        annual_net_income_by_year[fy] = {
                            'year': fy,
                            'net_income': net_income,
                            'fiscal_end': fiscal_end
                        }
                    elif end_year == fy:
                        # This entry's end date matches the fiscal year - prefer it
                        annual_net_income_by_year[fy] = {
                            'year': fy,
                            'net_income': net_income,
                            'fiscal_end': fiscal_end
                        }
        
        annual_net_income = list(annual_net_income_by_year.values())

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

        # Convert cumulative quarters to individual quarters
        # We process all years where we have quarterly data
        converted_quarterly = []
        
        all_years = set(quarterly_by_year.keys())
        
        for year in sorted(all_years, reverse=True):
            quarters_dict = {q['quarter']: q for q in quarterly_by_year.get(year, [])}
            annual_entry = annual_by_year.get(year)
            
            # Q1
            if 'Q1' in quarters_dict:
                q1_cumulative = quarters_dict['Q1']['net_income']
                converted_quarterly.append({
                    'year': year,
                    'quarter': 'Q1',
                    'net_income': q1_cumulative,
                    'fiscal_end': quarters_dict['Q1']['fiscal_end']
                })
                
                # Q2 (Needs Q1)
                if 'Q2' in quarters_dict:
                    q2_cumulative = quarters_dict['Q2']['net_income']
                    q2_individual = q2_cumulative - q1_cumulative
                    converted_quarterly.append({
                        'year': year,
                        'quarter': 'Q2',
                        'net_income': q2_individual,
                        'fiscal_end': quarters_dict['Q2']['fiscal_end']
                    })
                    
                    # Q3 (Needs Q2)
                    if 'Q3' in quarters_dict:
                        q3_cumulative = quarters_dict['Q3']['net_income']
                        q3_individual = q3_cumulative - q2_cumulative
                        converted_quarterly.append({
                            'year': year,
                            'quarter': 'Q3',
                            'net_income': q3_individual,
                            'fiscal_end': quarters_dict['Q3']['fiscal_end']
                        })
                        
                        # Q4 (Needs Annual + Q3)
                        if annual_entry:
                            annual_ni = annual_entry['net_income']
                            q4_individual = annual_ni - q3_cumulative
                            
                            # Add Q4
                            converted_quarterly.append({
                                'year': year,
                                'quarter': 'Q4',
                                'net_income': q4_individual,
                                'fiscal_end': annual_entry['fiscal_end']
                            })

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

    def parse_quarterly_revenue_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract quarterly Revenue history with Q4 calculated from annual data.

        EDGAR provides quarterly data in 10-Q filings (Q1, Q2, Q3) but Q4 is
        typically only reported in the annual 10-K. We calculate Q4 as:
        Q4 = Annual Revenue - (Q1 + Q2 + Q3)

        Revenue is reported cumulatively (YTD) in quarterly filings, so we
        convert to individual quarters: Q2_actual = Q2_cumulative - Q1, etc.

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter, revenue, and fiscal_end values
        """
        revenue_data_list = None

        # Try US-GAAP first (domestic companies) - multiple possible tags
        try:
            if 'us-gaap' in company_facts['facts']:
                # Try primary revenue tags in order of preference
                revenue_tags = [
                    'RevenueFromContractWithCustomerExcludingAssessedTax',  # ASC 606
                    'Revenues',  # General revenue tag
                    'SalesRevenueNet',  # Manufacturing/retail
                    'RevenuesNetOfInterestExpense', # Banks/Financials (e.g. MS)
                    'RevenueFromContractWithCustomerIncludingAssessedTax',
                ]
                
                revenue_data_list = []
                valid_tag_found = False
                
                for tag in revenue_tags:
                    if tag in company_facts['facts']['us-gaap']:
                        units = company_facts['facts']['us-gaap'][tag]['units']
                        if 'USD' in units:
                            revenue_data_list.extend(units['USD'])
                            valid_tag_found = True
                
                if not valid_tag_found:
                    revenue_data_list = None
        except (KeyError, TypeError):
            pass

        # Fall back to IFRS (foreign companies)
        if revenue_data_list is None:
            try:
                if 'ifrs-full' in company_facts['facts'] and 'Revenue' in company_facts['facts']['ifrs-full']:
                    units = company_facts['facts']['ifrs-full']['Revenue']['units']
                    if 'USD' in units:
                        revenue_data_list = units['USD']
                    else:
                        currency_units = [u for u in units.keys() if len(u) == 3 and u.isupper()]
                        if currency_units:
                            revenue_data_list = units[currency_units[0]]
            except (KeyError, TypeError):
                pass

        if revenue_data_list is None:
            logger.debug("Could not parse quarterly Revenue history from EDGAR")
            return []

        # Extract Q1, Q2, Q3 from quarterly reports (10-Q)
        quarterly_revenue = []
        seen_quarters = set()

        for entry in revenue_data_list:
            if entry.get('form') in ['10-Q', '6-K']:
                fiscal_end = entry.get('end')
                # Use fiscal year from EDGAR's fy field
                year = entry.get('fy')
                quarter = entry.get('fp')  # Fiscal period: Q1, Q2, Q3
                revenue = entry.get('val')

                if year and quarter and revenue is not None and (year, quarter) not in seen_quarters:
                    quarterly_revenue.append({
                        'year': year,
                        'quarter': quarter,
                        'revenue': revenue,
                        'fiscal_end': fiscal_end
                    })
                    seen_quarters.add((year, quarter))

        # Get annual data to calculate Q4
        annual_revenue_by_year = {}
        for entry in revenue_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fy = entry.get('fy')
                revenue = entry.get('val')
                fiscal_end = entry.get('end')
                start = entry.get('start')

                if fy and revenue is not None and fiscal_end and start:
                    try:
                        from datetime import datetime
                        d1 = datetime.strptime(start, '%Y-%m-%d')
                        d2 = datetime.strptime(fiscal_end, '%Y-%m-%d')
                        duration = (d2 - d1).days
                        if duration < 360:
                            continue  # Skip quarterly values
                    except (ValueError, TypeError):
                        continue

                    if fy not in annual_revenue_by_year:
                        annual_revenue_by_year[fy] = {
                            'year': fy,
                            'revenue': revenue,
                            'fiscal_end': fiscal_end
                        }

        # Convert cumulative quarters to individual quarters and calculate Q4
        annual_by_year = annual_revenue_by_year
        quarterly_by_year = {}
        for entry in quarterly_revenue:
            year = entry['year']
            if year not in quarterly_by_year:
                quarterly_by_year[year] = []
            quarterly_by_year[year].append(entry)

        converted_quarterly = []
        # Merge all years found in both sets
        all_years = set(annual_by_year.keys()) | set(quarterly_by_year.keys())

        for year in sorted(all_years, reverse=True):
            quarters = quarterly_by_year.get(year, [])
            quarters_dict = {q['quarter']: q for q in quarters}
            
            annual_entry = annual_by_year.get(year)

            # Case 1: Full year available (Standard)
            if annual_entry and all(f'Q{i}' in quarters_dict for i in [1, 2, 3]):
                q1_cumulative = quarters_dict['Q1']['revenue']
                q2_cumulative = quarters_dict['Q2']['revenue']
                q3_cumulative = quarters_dict['Q3']['revenue']
                annual_rev = annual_entry['revenue']

                q1_individual = q1_cumulative
                q2_individual = q2_cumulative - q1_cumulative
                q3_individual = q3_cumulative - q2_cumulative
                q4_individual = annual_rev - q3_cumulative

                calculated_annual = q1_individual + q2_individual + q3_individual + q4_individual
                if abs(calculated_annual - annual_rev) < 1000000:  # $1M tolerance
                    converted_quarterly.extend([
                        {'year': year, 'quarter': 'Q1', 'revenue': q1_individual, 'fiscal_end': quarters_dict['Q1']['fiscal_end']},
                        {'year': year, 'quarter': 'Q2', 'revenue': q2_individual, 'fiscal_end': quarters_dict['Q2']['fiscal_end']},
                        {'year': year, 'quarter': 'Q3', 'revenue': q3_individual, 'fiscal_end': quarters_dict['Q3']['fiscal_end']},
                        {'year': year, 'quarter': 'Q4', 'revenue': q4_individual, 'fiscal_end': annual_entry['fiscal_end']},
                    ])
            
            # Case 2: Incomplete year (e.g. current year with Q1, Q2, Q3 but no Annual)
            # Process whatever quarters we have
            elif not annual_entry and quarters:
                 # Sort quarters
                sorted_quarters = sorted(quarters, key=lambda x: x['quarter'])
                prev_cumulative = 0
                
                for q_data in sorted_quarters:
                    curr_cumulative = q_data['revenue']
                    individual_revenue = curr_cumulative - prev_cumulative
                    
                    converted_quarterly.append({
                        'year': year,
                        'quarter': q_data['quarter'],
                        'revenue': individual_revenue,
                        'fiscal_end': q_data['fiscal_end']
                    })
                    prev_cumulative = curr_cumulative

        quarterly_revenue = converted_quarterly

        def quarter_sort_key(entry):
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            return (-entry['year'], quarter_order.get(entry['quarter'], 0))

        quarterly_revenue.sort(key=quarter_sort_key)
        q4_count = sum(1 for entry in quarterly_revenue if entry['quarter'] == 'Q4')
        logger.info(f"Successfully parsed {len(quarterly_revenue)} quarters of Revenue data from EDGAR ({q4_count} Q4s calculated)")
        return quarterly_revenue

    def parse_quarterly_cash_flow_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract quarterly Cash Flow history (OCF, CapEx, FCF) with Q4 calculated from annual.

        EDGAR provides quarterly cash flow data in 10-Q filings.
        Q4 = Annual value - (Q1 + Q2 + Q3)

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter, ocf, capex, fcf, and fiscal_end
        """
        # 1. Extract Operating Cash Flow
        ocf_data = []
        try:
            if 'us-gaap' in company_facts['facts']:
                ocf_tags = [
                    'NetCashProvidedByUsedInOperatingActivities',
                    'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations',
                ]
                for tag in ocf_tags:
                    if tag in company_facts['facts']['us-gaap']:
                        units = company_facts['facts']['us-gaap'][tag]['units']
                        if 'USD' in units:
                            ocf_data.extend(units['USD'])
        except (KeyError, TypeError):
            pass

        # 2. Extract Capital Expenditures
        capex_data = []
        try:
            if 'us-gaap' in company_facts['facts']:
                capex_tags = [
                    'PaymentsToAcquirePropertyPlantAndEquipment',
                    'PaymentsToAcquireProductiveAssets',
                    'PaymentsForProceedsFromProductiveAssets', # Banks (MS)
                    'PaymentsToAcquireOtherProductiveAssets', # VZ (2019+)
                ]
                for tag in capex_tags:
                    if tag in company_facts['facts']['us-gaap']:
                        units = company_facts['facts']['us-gaap'][tag]['units']
                        if 'USD' in units:
                            capex_data.extend(units['USD'])
        except (KeyError, TypeError):
            pass

        def extract_quarterly_and_annual(data_list):
            """Extract quarterly cumulative values and annual totals"""
            quarterly = []
            annual_by_year = {}
            seen_quarters = set()

            for entry in data_list:
                form = entry.get('form')
                fiscal_end = entry.get('end')
                start = entry.get('start')
                val = entry.get('val')
                fy = entry.get('fy')
                fp = entry.get('fp')

                if val is None or not fiscal_end:
                    continue

                # Annual data (10-K)
                if form in ['10-K', '20-F'] and start:
                    try:
                        from datetime import datetime
                        d1 = datetime.strptime(start, '%Y-%m-%d')
                        d2 = datetime.strptime(fiscal_end, '%Y-%m-%d')
                        duration = (d2 - d1).days
                        if duration >= 360:
                            year = int(fiscal_end[:4])
                            if fy not in annual_by_year:
                                annual_by_year[fy] = {'val': val, 'fiscal_end': fiscal_end}
                    except (ValueError, TypeError):
                        pass

                # Quarterly data (10-Q)
                elif form in ['10-Q', '6-K'] and fp:
                    # PRIORITIZE FISCAL YEAR (fy) to align with Annual Report
                    # Only fallback to calendar year if fy is missing
                    year = fy if fy else (int(fiscal_end[:4]) if fiscal_end else None)
                    quarter = fp
                    if year and quarter and (year, quarter) not in seen_quarters:
                        quarterly.append({
                            'year': year,
                            'quarter': quarter,
                            'val': val,
                            'fiscal_end': fiscal_end
                        })
                        seen_quarters.add((year, quarter))

            return quarterly, annual_by_year

        def convert_cumulative_to_individual(quarterly, annual_by_year):
            """Convert cumulative YTD values to individual quarter values"""
            quarterly_by_year = {}
            for entry in quarterly:
                year = entry['year']
                if year not in quarterly_by_year:
                    quarterly_by_year[year] = []
                quarterly_by_year[year].append(entry)

            converted = []
            
            # Merge all years found
            all_years = set(annual_by_year.keys()) | set(quarterly_by_year.keys())
            
            for year in sorted(all_years, reverse=True):
                quarters = quarterly_by_year.get(year, [])
                quarters_dict = {q['quarter']: q for q in quarters}
                
                annual_entry = annual_by_year.get(year)

                # Case 1: Full year available (Standard)
                if annual_entry and all(f'Q{i}' in quarters_dict for i in [1, 2, 3]):
                    q1_cumulative = quarters_dict['Q1']['val']
                    q2_cumulative = quarters_dict['Q2']['val']
                    q3_cumulative = quarters_dict['Q3']['val']
                    annual_val = annual_entry['val']

                    q1_individual = q1_cumulative
                    q2_individual = q2_cumulative - q1_cumulative
                    q3_individual = q3_cumulative - q2_cumulative
                    q4_individual = annual_val - q3_cumulative

                    converted.extend([
                        {'year': year, 'quarter': 'Q1', 'val': q1_individual, 'fiscal_end': quarters_dict['Q1']['fiscal_end']},
                        {'year': year, 'quarter': 'Q2', 'val': q2_individual, 'fiscal_end': quarters_dict['Q2']['fiscal_end']},
                        {'year': year, 'quarter': 'Q3', 'val': q3_individual, 'fiscal_end': quarters_dict['Q3']['fiscal_end']},
                        {'year': year, 'quarter': 'Q4', 'val': q4_individual, 'fiscal_end': annual_entry['fiscal_end']},
                    ])
                
                # Case 2: Incomplete year (e.g. current year with Q1, Q2, Q3)
                # Process whatever quarters we have by differencing cumulative values
                elif not annual_entry and quarters:
                    # Sort quarters to process in order
                    sorted_quarters = sorted(quarters, key=lambda x: x['quarter'])
                    prev_cumulative = 0
                    
                    for q_data in sorted_quarters:
                        curr_cumulative = q_data['val']
                        individual_val = curr_cumulative - prev_cumulative
                        
                        converted.append({
                            'year': year,
                            'quarter': q_data['quarter'],
                            'val': individual_val,
                            'fiscal_end': q_data['fiscal_end']
                        })
                        prev_cumulative = curr_cumulative

            return converted

        # Process OCF and CapEx
        ocf_quarterly, ocf_annual = extract_quarterly_and_annual(ocf_data)
        capex_quarterly, capex_annual = extract_quarterly_and_annual(capex_data)

        ocf_converted = convert_cumulative_to_individual(ocf_quarterly, ocf_annual)
        capex_converted = convert_cumulative_to_individual(capex_quarterly, capex_annual)

        # Merge OCF and CapEx, calculate FCF
        ocf_by_key = {(e['year'], e['quarter']): e for e in ocf_converted}
        capex_by_key = {(e['year'], e['quarter']): e for e in capex_converted}

        all_keys = set(ocf_by_key.keys()) | set(capex_by_key.keys())
        result = []

        for key in all_keys:
            year, quarter = key
            ocf_entry = ocf_by_key.get(key)
            capex_entry = capex_by_key.get(key)

            ocf = ocf_entry['val'] if ocf_entry else None
            capex = capex_entry['val'] if capex_entry else None
            fiscal_end = (ocf_entry or capex_entry or {}).get('fiscal_end')

            fcf = None
            if ocf is not None and capex is not None:
                fcf = ocf - capex

            result.append({
                'year': year,
                'quarter': quarter,
                'operating_cash_flow': ocf,
                'capital_expenditures': capex,
                'free_cash_flow': fcf,
                'fiscal_end': fiscal_end
            })

        def quarter_sort_key(entry):
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            return (-entry['year'], quarter_order.get(entry['quarter'], 0))

        result.sort(key=quarter_sort_key)
        logger.info(f"Successfully parsed {len(result)} quarters of Cash Flow data from EDGAR")
        return result

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
        shares_data_list = []

        # Helper to safely extend shares list
        def collect_shares(namespace, tag):
            try:
                units = company_facts['facts'].get(namespace, {}).get(tag, {}).get('units', {})
                if 'shares' in units:
                    shares_data_list.extend(units['shares'])
                    logger.debug(f"Found {len(units['shares'])} entries for {tag}")
            except (KeyError, TypeError):
                pass

        # Collect from all known tags (Primary + Fallbacks)
        collect_shares('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding')
        collect_shares('us-gaap', 'CommonStockSharesOutstanding')
        collect_shares('dei', 'EntityCommonStockSharesOutstanding')
        
        # Also check IFRS
        collect_shares('ifrs-full', 'WeightedAverageNumberOfSharesOutstandingDiluted')

        # If zero data found
        if not shares_data_list:
            logger.debug("Could not parse shares outstanding history from EDGAR: No known tags found")
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
        shares_data_list = []

        # Helper to safely extend shares list
        def collect_shares(namespace, tag):
            try:
                units = company_facts['facts'].get(namespace, {}).get(tag, {}).get('units', {})
                if 'shares' in units:
                    shares_data_list.extend(units['shares'])
            except (KeyError, TypeError):
                pass
        
        # Collect from all known tags (Primary + Fallbacks)
        collect_shares('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding')
        collect_shares('us-gaap', 'CommonStockSharesOutstanding')
        collect_shares('dei', 'EntityCommonStockSharesOutstanding')
        collect_shares('ifrs-full', 'WeightedAverageNumberOfSharesOutstandingDiluted')

        # If we still don't have data, return empty
        if not shares_data_list:
            logger.debug("Could not parse quarterly shares outstanding history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Extract quarterly reports (10-Q for US, 6-K for foreign)
        quarterly_shares = []
        seen_quarters = set()

        for entry in shares_data_list:
            if entry.get('form') in ['10-Q', '6-K']:
                fiscal_end = entry.get('end')
                # Use fiscal year from EDGAR's fy field
                year = entry.get('fy')
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
                # Use fiscal_end date for year determination to ensure historical data points
                # in current filings (e.g. 2022 data in 2024 10-K) are assigned to right year.
                year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
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
            
            # IMPUTATION: If Q1, Q2, Q3 are completely missing (e.g. HSY where 10-Q tags are absent),
            # fill them with the Annual value. This allows EPS calculation for those quarters.
            shares = annual_entry['shares']
            # Only impute if we have NO data for these quarters
            # We don't have exact fiscal_end dates, so use None or approximate? None is safer.
            for q in ['Q1', 'Q2', 'Q3']:
                 if (year, q) not in seen_quarters:
                     quarterly_shares.append({
                        'year': year,
                        'quarter': q,
                        'shares': shares,
                        'fiscal_end': None # Date unknown, but not needed for EPS calculation matching
                     })
                     logger.debug(f"Imputed {q} shares for {year} using Annual value: {shares:,.0f}")

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

    def calculate_quarterly_eps_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate quarterly EPS from Net Income and Shares Outstanding.
        Fallback for when reported EPS tags are missing (e.g. HSY).
        """
        # Get Quarterly Net Income
        net_income_quarterly = self.parse_quarterly_net_income_history(company_facts)
        
        # Get Quarterly Shares
        shares_quarterly = self.parse_quarterly_shares_outstanding_history(company_facts)
        
        # Create lookup for shares by (year, quarter)
        shares_lookup = {(e['year'], e['quarter']): e['shares'] for e in shares_quarterly}
        
        eps_history = []
        for ni in net_income_quarterly:
            key = (ni['year'], ni['quarter'])
            if key in shares_lookup:
                shares = shares_lookup[key]
                if shares > 0:
                    eps = ni['net_income'] / shares
                    eps_history.append({
                        'year': ni['year'],
                        'quarter': ni['quarter'],
                        'eps': eps,
                        'fiscal_end': ni['fiscal_end']
                    })
                    
        eps_history.sort(key=lambda x: (x['year'], x['quarter']), reverse=True)
        return eps_history

    def parse_interest_expense(self, company_facts: Dict[str, Any]) -> Optional[float]:
        """
        Extract the most recent annual Interest Expense from company facts.
        
        Args:
            company_facts: Company facts data from EDGAR API
            
        Returns:
            Most recent annual interest expense (absolute value) or None
        """
        interest_data_list = []
        
        # Try US-GAAP first
        try:
            if 'us-gaap' in company_facts['facts']:
                # Tags for Interest Expense
                tags = [
                    'InterestExpense',
                    'InterestAndDebtExpense', 
                    'InterestExpenseDebt'
                ]
                
                for tag in tags:
                    if tag in company_facts['facts']['us-gaap']:
                        units = company_facts['facts']['us-gaap'][tag]['units']
                        if 'USD' in units:
                            interest_data_list.extend(units['USD'])
                            logger.debug(f"Found interest expense using US-GAAP tag: {tag}")
                            
        except (KeyError, TypeError):
            pass
            
        # Try IFRS
        if not interest_data_list:
            try:
                if 'ifrs-full' in company_facts['facts']:
                    tags = [
                        'FinanceCosts',
                        'InterestExpense'
                    ]
                    
                    for tag in tags:
                        if tag in company_facts['facts']['ifrs-full']:
                            units = company_facts['facts']['ifrs-full'][tag]['units']
                            # Find USD or first currency
                            if 'USD' in units:
                                interest_data_list = units['USD']
                            else:
                                 currency_units = [u for u in units.keys() if len(u) == 3 and u.isupper()]
                                 if currency_units:
                                     interest_data_list = units[currency_units[0]]
            except (KeyError, TypeError):
                pass
                
        if not interest_data_list:
            logger.debug("Could not parse Interest Expense from EDGAR")
            return None
            
        # Find the latest annual entry
        latest_year = 0
        latest_val = None
        
        for entry in interest_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                try:
                    fiscal_end = entry.get('end')
                    # Calculate duration to ensure it's annual
                    start = entry.get('start')
                    if start and fiscal_end:
                         from datetime import datetime
                         d1 = datetime.strptime(start, '%Y-%m-%d')
                         d2 = datetime.strptime(fiscal_end, '%Y-%m-%d')
                         duration = (d2 - d1).days
                         if duration < 360:
                             continue
                             
                    year = int(fiscal_end[:4]) if fiscal_end else entry.get('fy')
                    val = entry.get('val')
                    
                    if year and val is not None:
                        if year > latest_year:
                             latest_year = year
                             latest_val = val
                        elif year == latest_year:
                             # Prefer latest fiscal end date (restatement)
                             if fiscal_end and (not latest_val or fiscal_end > str(latest_val)):
                                  latest_val = val
                except (ValueError, TypeError):
                    continue
                    
        if latest_val is not None:
             logger.info(f"Found EDGAR Interest Expense for {latest_year}: ${latest_val:,.0f}")
             return abs(float(latest_val))
             
        return None

    def parse_shareholder_equity_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract Shareholder Equity history from company facts.
        
        Args:
            company_facts: Company facts data from EDGAR API
            
        Returns:
            List of dictionaries with year, shareholder_equity, and fiscal_end values
        """
        equity_data_list = None
        
        # Try US-GAAP first
        try:
            # Try StockholdersEquity first (most common)
            if 'us-gaap' in company_facts['facts']:
                if 'StockholdersEquity' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['StockholdersEquity']['units']
                    if 'USD' in units:
                        equity_data_list = units['USD']
                
                # Fallback: StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest
                if equity_data_list is None and 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']['units']
                    if 'USD' in units:
                         equity_data_list = units['USD']

        except (KeyError, TypeError):
            pass
            
        # Try IFRS
        if equity_data_list is None:
            try:
                if 'ifrs-full' in company_facts['facts']:
                    if 'Equity' in company_facts['facts']['ifrs-full']:
                        units = company_facts['facts']['ifrs-full']['Equity']['units']
                        if 'USD' in units:
                            equity_data_list = units['USD']
                        else:
                            # Find first currency unit
                            currency_units = [u for u in units.keys() if len(u) == 3 and u.isupper()]
                            if currency_units:
                                equity_data_list = units[currency_units[0]]
            except (KeyError, TypeError):
                pass
                
        if equity_data_list is None:
            logger.debug("Could not parse Shareholder Equity history from EDGAR")
            return []
            
        # Process and filter for annual data
        annual_equity_by_year = {}
        
        for entry in equity_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fiscal_end = entry.get('end')
                val = entry.get('val')
                start = entry.get('start')  # Equity is a point-in-time metric, but EDGAR might provide period
                
                # For point-in-time metrics like Equity, we care about the 'end' date matching the fiscal year end
                if val is not None and fiscal_end:
                     year = int(fiscal_end[:4])
                     
                     # Keep entry for each unique fiscal_end, preferring later entries (restatements)
                     if fiscal_end not in annual_equity_by_year:
                         annual_equity_by_year[fiscal_end] = {
                             'year': year,
                             'shareholder_equity': val,
                             'fiscal_end': fiscal_end
                         }
        
        # Group by year
        by_year = {}
        for fiscal_end, entry in annual_equity_by_year.items():
            year = entry['year']
            # Prefer the latest fiscal_end for the year if duplicates exist (unlikely for annual)
            if year not in by_year:
                by_year[year] = entry
                
        annual_equity = list(by_year.values())
        annual_equity.sort(key=lambda x: x['year'], reverse=True)
        
        logger.info(f"Successfully parsed {len(annual_equity)} years of Shareholder Equity from EDGAR")
        return annual_equity

    def parse_quarterly_shareholder_equity_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract Quarterly Shareholder Equity history from company facts.
        
        Args:
            company_facts: Company facts data from EDGAR API
            
        Returns:
            List of dictionaries with year, quarter, shareholder_equity, and fiscal_end values
        """
        equity_data_list = []
        
        # Helper to safely extend list
        def collect_equity(namespace, tag):
            try:
                units = company_facts['facts'].get(namespace, {}).get(tag, {}).get('units', {})
                if 'USD' in units:
                    equity_data_list.extend(units['USD'])
            except (KeyError, TypeError):
                pass

        # Try US-GAAP first
        try:
            collect_equity('us-gaap', 'StockholdersEquity')
            collect_equity('us-gaap', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest')
            collect_equity('us-gaap', 'Equity') # Generic fallback
        except (KeyError, TypeError):
            pass

        except (KeyError, TypeError):
            pass
            
        # Try IFRS
        if equity_data_list is None:
            try:
                if 'ifrs-full' in company_facts['facts']:
                    if 'Equity' in company_facts['facts']['ifrs-full']:
                        units = company_facts['facts']['ifrs-full']['Equity']['units']
                        if 'USD' in units:
                            equity_data_list = units['USD']
                        else:
                            # Find first currency unit
                            currency_units = [u for u in units.keys() if len(u) == 3 and u.isupper()]
                            if currency_units:
                                equity_data_list = units[currency_units[0]]
            except (KeyError, TypeError):
                pass
                
        if equity_data_list is None:
            logger.debug("Could not parse Quarterly Shareholder Equity history from EDGAR")
            return []
            
        # Process and filter for quarterly data
        quarterly_equity = []
        seen_quarters = set()
        
        for entry in equity_data_list:
            form = entry.get('form')
            # Accept 10-Q (Quarterly) and 10-K (Annual/Q4)
            if form in ['10-Q', '10-K', '20-F', '40-F', '6-K']:
                fiscal_end = entry.get('end')
                val = entry.get('val')
                year = entry.get('fy')
                fp = entry.get('fp') # Q1, Q2, Q3, FY/Q4
                
                if not year or not fp or val is None or not fiscal_end:
                    continue
                    
                quarter = None
                if fp in ['Q1', 'Q2', 'Q3']:
                    quarter = fp
                elif fp in ['Q4', 'FY'] and form in ['10-K', '20-F', '40-F']:
                    # For Equity (point-in-time), FY end value IS Q4 end value
                    quarter = 'Q4'
                
                if quarter:
                    if (year, quarter) not in seen_quarters:
                        quarterly_equity.append({
                            'year': year,
                            'quarter': quarter,
                            'shareholder_equity': val,
                            'fiscal_end': fiscal_end
                        })
                        seen_quarters.add((year, quarter))
        
        # Sort by year desc, then quarter desc
        def quarter_sort_key(entry):
            quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
            return (-entry['year'], -quarter_order.get(entry['quarter'], 0))
            
        quarterly_equity.sort(key=quarter_sort_key)
        
        logger.info(f"Successfully parsed {len(quarterly_equity)} quarters of Shareholder Equity from EDGAR")
        return quarterly_equity

    def parse_cash_equivalents_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract Cash and Cash Equivalents history from company facts.

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, cash_and_cash_equivalents, and fiscal_end values
        """
        cash_data_list = None

        # Try US-GAAP first
        try:
            if 'us-gaap' in company_facts['facts']:
                # Try CashAndCashEquivalentsAtCarryingValue first (most common)
                if 'CashAndCashEquivalentsAtCarryingValue' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['CashAndCashEquivalentsAtCarryingValue']['units']
                    if 'USD' in units:
                        cash_data_list = units['USD']

                # Fallback: CashAndCashEquivalents
                if cash_data_list is None and 'CashAndCashEquivalents' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['CashAndCashEquivalents']['units']
                    if 'USD' in units:
                        cash_data_list = units['USD']

                # Fallback: Cash (less common, but some companies use it)
                if cash_data_list is None and 'Cash' in company_facts['facts']['us-gaap']:
                    units = company_facts['facts']['us-gaap']['Cash']['units']
                    if 'USD' in units:
                        cash_data_list = units['USD']

        except (KeyError, TypeError):
            pass

        # Try IFRS
        if cash_data_list is None:
            try:
                if 'ifrs-full' in company_facts['facts']:
                    if 'CashAndCashEquivalents' in company_facts['facts']['ifrs-full']:
                        units = company_facts['facts']['ifrs-full']['CashAndCashEquivalents']['units']
                        if 'USD' in units:
                            cash_data_list = units['USD']
                        else:
                            # Find first currency unit
                            currency_units = [u for u in units.keys() if len(u) == 3 and u.isupper()]
                            if currency_units:
                                cash_data_list = units[currency_units[0]]
            except (KeyError, TypeError):
                pass

        if cash_data_list is None:
            logger.debug("Could not parse Cash and Cash Equivalents history from EDGAR")
            return []

        # Process and filter for annual data
        annual_cash_by_fiscal_end = {}

        for entry in cash_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                fiscal_end = entry.get('end')
                val = entry.get('val')

                # For point-in-time metrics like Cash, we care about the 'end' date matching the fiscal year end
                if val is not None and fiscal_end:
                    # Keep entry for each unique fiscal_end, preferring later entries (restatements)
                    if fiscal_end not in annual_cash_by_fiscal_end:
                        annual_cash_by_fiscal_end[fiscal_end] = {
                            'fiscal_end': fiscal_end,
                            'cash_and_cash_equivalents': val
                        }

        # Group by year
        by_year = {}
        for fiscal_end, entry in annual_cash_by_fiscal_end.items():
            year = int(fiscal_end[:4])
            entry['year'] = year
            # Prefer the latest fiscal_end for the year if duplicates exist
            if year not in by_year:
                by_year[year] = entry

        annual_cash = list(by_year.values())
        annual_cash.sort(key=lambda x: x['year'], reverse=True)

        logger.info(f"Successfully parsed {len(annual_cash)} years of Cash and Cash Equivalents from EDGAR")
        return annual_cash

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

        except Exception as e:
            logger.warning(f"Error parsing D/E history: {e}")
            return []

    def parse_quarterly_debt_to_equity_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract quarterly debt-to-equity ratios from company facts (10-Q/6-K)

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, quarter, debt_to_equity, and fiscal_end values
        """
        try:
            facts = company_facts['facts']['us-gaap']

            # Get equity data
            equity_tags = [
                'StockholdersEquity',
                'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
                'CommonStockholdersEquity',
                'LiabilitiesAndStockholdersEquity'
            ]

            equity_data = []
            for tag in equity_tags:
                equity_data = facts.get(tag, {}).get('units', {}).get('USD', [])
                if equity_data:
                    break

            if not equity_data:
                return []

            # Get debt data (Long Term)
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

            # Get short-term debt data
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

            # Helper to organize by (year, quarter)
            def organize_by_quarter_first_wins(data_list):
                organized = {}
                for entry in data_list:
                    form = entry.get('form')
                    fiscal_end = entry.get('end')
                    if not fiscal_end:
                        continue
                        
                    fp = entry.get('fp')
                    val = entry.get('val')
                    
                    is_quarterly_form = form in ['10-Q', '6-K']
                    is_annual_form = form in ['10-K', '20-F', '40-F']
                    
                    quarter = None
                    if is_quarterly_form:
                        quarter = fp
                    elif is_annual_form:
                        quarter = 'Q4'
                    
                    if not quarter or not quarter.startswith('Q'):
                        continue
                        
                    year = int(fiscal_end[:4])
                    key = (year, quarter)
                    
                    if key not in organized and val is not None:
                        organized[key] = {'val': val, 'fiscal_end': fiscal_end}
                return organized

            equity_org = organize_by_quarter_first_wins(equity_data)
            lt_debt_org = organize_by_quarter_first_wins(long_term_debt_data)
            st_debt_org = organize_by_quarter_first_wins(short_term_debt_data)

            quarterly_de = []
            
            # Iterate through all quarters we found equity for
            for key in equity_org:
                year, quarter = key
                equity = equity_org[key]['val']
                fiscal_end = equity_org[key]['fiscal_end']
                
                total_debt = 0
                has_debt_data = False
                
                if key in lt_debt_org:
                    total_debt += lt_debt_org[key]['val']
                    has_debt_data = True
                    
                if key in st_debt_org:
                    total_debt += st_debt_org[key]['val']
                    has_debt_data = True
                
                if equity != 0 and has_debt_data:
                    de_ratio = total_debt / equity
                    quarterly_de.append({
                        'year': year,
                        'quarter': quarter,
                        'debt_to_equity': de_ratio,
                        'fiscal_end': fiscal_end
                    })
            
            # Sort
            def q_sort_key(x):
                q_map = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
                return (x['year'], q_map.get(x['quarter'], 0))
            
            quarterly_de.sort(key=q_sort_key, reverse=True)
            
            logger.info(f"Successfully parsed {len(quarterly_de)} quarters of D/E data")
            return quarterly_de

        except Exception as e:
            logger.error(f"Error parsing quarterly D/E history: {e}")
            return []

    def parse_effective_tax_rate(self, company_facts: Dict[str, Any]) -> Optional[float]:
        """
        Extract the most recent annual Effective Tax Rate from company facts.
        Formula: Income Tax Expense / Pretax Income
        
        Args:
            company_facts: Company facts data from EDGAR API
            
        Returns:
            Most recent annual effective tax rate (as decimal, e.g. 0.21) or None
        """
        # Fetch Income Tax Provision
        tax_tags = ['IncomeTaxExpenseBenefit', 'IncomeTaxExpenseBenefitContinuingOperations']
        tax_data = []
        
        try:
            if 'us-gaap' in company_facts['facts']:
                for tag in tax_tags:
                    if tag in company_facts['facts']['us-gaap']:
                        units = company_facts['facts']['us-gaap'][tag]['units']
                        if 'USD' in units:
                            tax_data.extend(units['USD'])
        except (KeyError, TypeError):
            pass
            
        # Fetch Pretax Income
        pretax_tags = [
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxes'
        ]
        pretax_data = []
        
        try:
             if 'us-gaap' in company_facts['facts']:
                for tag in pretax_tags:
                    if tag in company_facts['facts']['us-gaap']:
                        units = company_facts['facts']['us-gaap'][tag]['units']
                        if 'USD' in units:
                            pretax_data.extend(units['USD'])
        except (KeyError, TypeError):
             pass
             
        if not tax_data or not pretax_data:
            return None
            
        # Create lookups by year
        def get_annual_map(data_list):
            annual_map = {}
            for entry in data_list:
                if entry.get('form') in ['10-K', '20-F']:
                     fiscal_end = entry.get('end')
                     start = entry.get('start')
                     val = entry.get('val')
                     
                     if not fiscal_end or not start or val is None:
                         continue
                         
                     # Check duration (~360 days)
                     try:
                         from datetime import datetime
                         d1 = datetime.strptime(start, '%Y-%m-%d')
                         d2 = datetime.strptime(fiscal_end, '%Y-%m-%d')
                         duration = (d2 - d1).days
                         if duration < 300:
                             continue
                             
                         year = int(fiscal_end[:4])
                         # Keep latest
                         if year not in annual_map or fiscal_end > annual_map[year]['end']:
                             annual_map[year] = {'val': val, 'end': fiscal_end}
                     except:
                         continue
            return annual_map
            
        tax_map = get_annual_map(tax_data)
        pretax_map = get_annual_map(pretax_data)
        
        # Find latest common year
        years = sorted(list(set(tax_map.keys()) & set(pretax_map.keys())), reverse=True)
        
        if years:
            latest_year = years[0]
            tax = tax_map[latest_year]['val']
            pretax = pretax_map[latest_year]['val']
            
            if pretax and pretax != 0:
                rate = tax / pretax
                # Cap at reasonable bounds (e.g. 0 to 100%, sometimes negative if tax benefit)
                # But keep it raw for now, maybe just log it
                logger.info(f"Calculated EDGAR effective tax rate for {latest_year}: {rate:.2%}")
                return rate
                
        return None

    def _extract_quarterly_from_raw_xbrl(self, ticker: str, income_statement, fiscal_year: int = None, fiscal_quarter: str = None) -> Dict[str, Any]:
        """
        Extract discrete quarterly values from income statement using get_raw_data().
        
        In edgartools 5.x, to_dataframe() no longer provides (Q) column suffixes.
        Instead, we use get_raw_data() which provides values with period keys like:
        - 'duration_2025-04-01_2025-06-30' for Q2 discrete (3 months)
        - 'duration_2025-01-01_2025-06-30' for 6-month YTD
        
        We identify quarterly values by finding periods with ~90 day duration.
        """
        result = {
            'revenue': None,
            'net_income': None,
            'eps': None,
            'fiscal_year': fiscal_year,
            'fiscal_quarter': fiscal_quarter,
            'fiscal_end': None
        }
        
        try:
            raw_data = income_statement.get_raw_data()
        except Exception as e:
            logger.warning(f"[{ticker}] Failed to get raw XBRL data: {e}")
            return result
        
        quarter_period_key = None
        
        for item in raw_data:
            if not item.get('has_values') or item.get('is_abstract'):
                continue
            
            label = item.get('label', '')
            concept = item.get('concept', '')
            values = item.get('values', {})
            
            # Skip dimensional breakdowns (segments) - we want total values only
            if item.get('is_dimension', False):
                continue
            
            # Check if this is a revenue concept (not cost)
            is_revenue = ('revenue' in label.lower() or 
                         concept.lower() == 'us-gaap_revenues')
            is_cost = 'cost' in label.lower()
            
            if is_revenue and not is_cost and not result['revenue']:
                # Find the discrete quarterly value (shortest duration period)
                quarterly_periods = []
                for period_key, val in values.items():
                    if period_key.startswith('duration_'):
                        parts = period_key.replace('duration_', '').split('_')
                        if len(parts) == 2:
                            start_date = parts[0]
                            end_date = parts[1]
                            from datetime import datetime
                            try:
                                start = datetime.strptime(start_date, '%Y-%m-%d')
                                end = datetime.strptime(end_date, '%Y-%m-%d')
                                duration_days = (end - start).days
                                quarterly_periods.append({
                                    'key': period_key,
                                    'value': val,
                                    'start': start_date,
                                    'end': end_date,
                                    'duration_days': duration_days
                                })
                            except:
                                pass
                
                if quarterly_periods:
                    # Sort by end date (most recent first), then by duration (shortest = discrete quarterly)
                    quarterly_periods.sort(key=lambda x: (-int(x['end'].replace('-', '')), x['duration_days']))
                    
                    # Pick the first one that's a 3-month period (80-100 days)
                    for qp in quarterly_periods:
                        if 80 <= qp['duration_days'] <= 100:
                            result['revenue'] = qp['value']
                            quarter_period_key = qp['key']
                            result['fiscal_end'] = qp['end']
                            logger.info(f"[{ticker}] Found discrete quarterly revenue: ${qp['value']/1e9:.2f}B from {qp['start']} to {qp['end']} ({qp['duration_days']} days)")
                            break
            
            # Check for net income
            is_net_income = ('net income' in label.lower() and 
                           'per share' not in label.lower() and
                           'comprehensive' not in label.lower())
            
            if is_net_income and not result['net_income'] and quarter_period_key:
                if quarter_period_key in values:
                    result['net_income'] = values[quarter_period_key]
                    logger.info(f"[{ticker}] Found discrete quarterly Net Income: ${result['net_income']/1e9:.2f}B")
            
            # Check for EPS (diluted)
            is_eps = ('earnings per share' in label.lower() and 'diluted' in label.lower())
            
            if is_eps and not result['eps'] and quarter_period_key:
                if quarter_period_key in values:
                    result['eps'] = values[quarter_period_key]
                    logger.info(f"[{ticker}] Found discrete quarterly EPS: ${result['eps']:.2f}")
        
        # Infer fiscal quarter from fiscal_end date if not provided
        if result['fiscal_end'] and not result['fiscal_quarter']:
            try:
                m = int(result['fiscal_end'].split('-')[1])
                if m in [1, 2, 3]: result['fiscal_quarter'] = 'Q1'
                elif m in [4, 5, 6]: result['fiscal_quarter'] = 'Q2'
                elif m in [7, 8, 9]: result['fiscal_quarter'] = 'Q3'
                else: result['fiscal_quarter'] = 'Q4'
                result['fiscal_year'] = int(result['fiscal_end'].split('-')[0])
            except:
                pass
        
        return result



    def get_quarterly_financials_from_10q(self, ticker: str, num_quarters: int = 8) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract quarterly financials directly from 10-Q filings using edgartools.
        
        This method bypasses the outdated company_facts API and parses 10-Q filings
        directly to extract all quarterly financial metrics. This solves issues with:
        - Missing data for companies like AAPL/MSFT (company_facts is outdated)
        - Incorrect data for companies like NFLX (prior-year comparatives)
        - Inconsistent XBRL tags across companies
        
        Args:
            ticker: Stock ticker symbol
            num_quarters: Number of recent quarters to extract (default: 8 = 2 years)
        
        Returns:
            Dictionary containing quarterly data lists:
            - revenue_quarterly: List of {year, quarter, revenue, fiscal_end}
            - eps_quarterly: List of {year, quarter, eps, fiscal_end}
            - net_income_quarterly: List of {year, quarter, net_income, fiscal_end}
            - cash_flow_quarterly: List of {year, quarter, operating_cash_flow, capital_expenditures, free_cash_flow, fiscal_end}
            - debt_to_equity_quarterly: List of {year, quarter, debt_to_equity, fiscal_end}
            - shares_outstanding_quarterly: List of {year, quarter, shares, fiscal_end}
            - shareholder_equity_quarterly: List of {year, quarter, shareholder_equity, fiscal_end}
        """
        try:
            # Get company object
            cik = self.get_cik_for_ticker(ticker)
            if not cik:
                logger.warning(f"[{ticker}] Could not find CIK")
                return {}
            
            company = self.get_company(cik)
            if not company:
                logger.warning(f"[{ticker}] Could not create Company object")
                return {}
            
            # Get recent 10-Q filings
            filings = company.get_filings(form="10-Q").head(num_quarters)
            
            if not filings or len(filings) == 0:
                logger.warning(f"[{ticker}] No 10-Q filings found")
                return {}
            
            logger.info(f"[{ticker}] Found {len(filings)} 10-Q filings for extraction")
            
            # Initialize result lists
            revenue_quarterly = []
            eps_quarterly = []
            net_income_quarterly = []
            cash_flow_quarterly = []
            debt_to_equity_quarterly = []
            shares_outstanding_quarterly = []
            shareholder_equity_quarterly = []
            
            # Process each filing
            for filing in filings:
                try:
                    # Get XBRL data
                    xbrl = filing.xbrl()
                    if not xbrl:
                        logger.debug(f"[{ticker}] No XBRL data for filing {filing.filing_date}")
                        continue
                    
                    statements = xbrl.statements
                    
                    # Get fiscal period info from cover page
                    cover = statements.cover_page()
                    cover_df = cover.to_dataframe() if cover else None
                    
                    # Extract fiscal year and quarter
                    fiscal_year = None
                    fiscal_quarter = None
                    fiscal_end = None
                    
                    if cover_df is not None and 'label' in cover_df.columns:
                        # Find DocumentFiscalYearFocus and DocumentFiscalPeriodFocus
                        for idx, row in cover_df.iterrows():
                            label = row.get('label', '')
                            if 'Fiscal Year' in label or 'Document Fiscal Year' in label:
                                # Get the value from the first data column
                                data_cols = [col for col in cover_df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                                if data_cols:
                                    fiscal_year = row.get(data_cols[0])
                                    if fiscal_year and isinstance(fiscal_year, str):
                                        try:
                                            fiscal_year = int(fiscal_year)
                                        except:
                                            pass
                            elif 'Fiscal Period' in label or 'Document Fiscal Period' in label:
                                data_cols = [col for col in cover_df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                                if data_cols:
                                    fiscal_quarter = row.get(data_cols[0])
                            elif 'Document Period End Date' in label:
                                data_cols = [col for col in cover_df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                                if data_cols:
                                    fiscal_end = row.get(data_cols[0])
                    
                    # Fallback: extract from income statement column name if not in cover page
                    if not fiscal_year or not fiscal_quarter:
                        # Try to get fiscal_end from income statement column
                        income = statements.income_statement()
                        if income:
                            income_df = income.to_dataframe()
                            if 'label' in income_df.columns:
                                quarterly_cols = [col for col in income_df.columns if isinstance(col, str) and '(Q' in col]
                                if quarterly_cols:
                                    quarterly_col = quarterly_cols[0]
                                    # Extract fiscal_end from column name like "2025-09-30 (Q3)"
                                    if '-' in quarterly_col:
                                        fiscal_end = quarterly_col.split(' ')[0]
                                        # Extract year from fiscal_end
                                        fiscal_year = int(fiscal_end[:4])
                                        
                                        # Calculate fiscal quarter based on fiscal year end
                                        # We need to determine the company's fiscal year end month
                                        # Look for the most recent 10-K to determine fiscal year end
                                        try:
                                            tenk_filings = company.get_filings(form="10-K").head(1)
                                            if tenk_filings and len(tenk_filings) > 0:
                                                tenk_filing = tenk_filings[0]
                                                tenk_xbrl = tenk_filing.xbrl()
                                                if tenk_xbrl:
                                                    tenk_income = tenk_xbrl.statements.income_statement()
                                                    if tenk_income:
                                                        tenk_df = tenk_income.to_dataframe()
                                                        # Find annual column (no Q in name)
                                                        annual_cols = [col for col in tenk_df.columns if isinstance(col, str) and '-' in col and '(Q' not in col and col != 'level']
                                                        if annual_cols:
                                                            # Get fiscal year end date from 10-K
                                                            fye_date = annual_cols[0]  # e.g., "2024-06-30"
                                                            fye_month = int(fye_date[5:7])  # Extract month
                                                            
                                                            # Calculate fiscal quarter based on period end month
                                                            period_end_month = int(fiscal_end[5:7])
                                                            
                                                            # Calculate months from fiscal year end
                                                            # Fiscal Q1 = 1-3 months after FYE
                                                            # Fiscal Q2 = 4-6 months after FYE
                                                            # Fiscal Q3 = 7-9 months after FYE
                                                            # Fiscal Q4 = 10-12 months after FYE (ends at FYE)
                                                            
                                                            months_from_fye = (period_end_month - fye_month) % 12
                                                            if months_from_fye == 0:
                                                                months_from_fye = 12  # Period ending at FYE is Q4
                                                            
                                                            if months_from_fye <= 3:
                                                                fiscal_quarter = "Q1"
                                                            elif months_from_fye <= 6:
                                                                fiscal_quarter = "Q2"
                                                            elif months_from_fye <= 9:
                                                                fiscal_quarter = "Q3"
                                                            else:
                                                                fiscal_quarter = "Q4"
                                                            
                                                            logger.debug(f"[{ticker}] Calculated fiscal quarter: FYE month={fye_month}, period_end month={period_end_month}, months_from_fye={months_from_fye}, fiscal_quarter={fiscal_quarter}")
                                        except Exception as e:
                                            logger.debug(f"[{ticker}] Could not determine fiscal year end: {e}")
                                            # Do not use quarterly_col here, it is not defined yet
                    
                    # Extract from Income Statement
                    # Always fetch the income statement for data extraction
                    income = statements.income_statement()
                    
                    if income:
                        # Use new edgartools 5.x compatible extraction via get_raw_data()
                        extracted = self._extract_quarterly_from_raw_xbrl(
                            ticker, income, fiscal_year, fiscal_quarter
                        )
                        
                        # Update fiscal info from extraction if not already set
                        if not fiscal_year and extracted['fiscal_year']:
                            fiscal_year = extracted['fiscal_year']
                        if not fiscal_quarter and extracted['fiscal_quarter']:
                            fiscal_quarter = extracted['fiscal_quarter']
                        if not fiscal_end and extracted['fiscal_end']:
                            fiscal_end = extracted['fiscal_end']
                        
                        # Store extracted values
                        if extracted['revenue'] and extracted['revenue'] > 0 and fiscal_year and fiscal_quarter:
                            revenue_quarterly.append({
                                'year': fiscal_year,
                                'quarter': fiscal_quarter,
                                'revenue': extracted['revenue'],
                                'fiscal_end': fiscal_end
                            })
                        
                        if extracted['net_income'] is not None and fiscal_year and fiscal_quarter:
                            net_income_quarterly.append({
                                'year': fiscal_year,
                                'quarter': fiscal_quarter,
                                'net_income': extracted['net_income'],
                                'fiscal_end': fiscal_end
                            })
                        
                        if extracted['eps'] is not None and fiscal_year and fiscal_quarter:
                            eps_quarterly.append({
                                'year': fiscal_year,
                                'quarter': fiscal_quarter,
                                'eps': extracted['eps'],
                                'fiscal_end': fiscal_end
                            })
                        
                        # Skip the old to_dataframe based extraction below
                        # (Balance sheet and cash flow extraction follows)
                    

                    # Extract from Balance Sheet
                    balance_sheet = statements.balance_sheet()
                    if balance_sheet:
                        bs_df = balance_sheet.to_dataframe()
                        
                        if 'label' in bs_df.columns:
                            # Find quarterly column
                            quarterly_cols = [col for col in bs_df.columns if isinstance(col, str) and '(Q' in col]
                            
                            if quarterly_cols:
                                quarterly_col = quarterly_cols[0]
                                
                                # Extract Total Debt
                                debt_rows = bs_df[bs_df['label'].str.contains('Debt', case=False, na=False) & 
                                                 bs_df['label'].str.contains('Total', case=False, na=False)]
                                
                                total_debt = None
                                for idx in range(len(debt_rows)):
                                    debt_row = debt_rows.iloc[idx]
                                    if 'abstract' in bs_df.columns and debt_row.get('abstract', False):
                                        continue
                                    debt = debt_row[quarterly_col]
                                    if isinstance(debt, str):
                                        if debt.strip() == '':
                                            continue
                                        try:
                                            debt = float(debt.replace(',', ''))
                                        except:
                                            continue
                                    if debt and debt > 0:
                                        total_debt = debt
                                        break
                                
                                # Extract Shareholder Equity
                                equity_rows = bs_df[bs_df['label'].str.contains('Equity', case=False, na=False) & 
                                                   (bs_df['label'].str.contains('Stockholders', case=False, na=False) | 
                                                    bs_df['label'].str.contains('Shareholders', case=False, na=False) |
                                                    bs_df['label'].str.contains('Total Equity', case=False, na=False))]
                                
                                shareholder_equity = None
                                for idx in range(len(equity_rows)):
                                    equity_row = equity_rows.iloc[idx]
                                    if 'abstract' in bs_df.columns and equity_row.get('abstract', False):
                                        continue
                                    equity = equity_row[quarterly_col]
                                    if isinstance(equity, str):
                                        if equity.strip() == '':
                                            continue
                                        try:
                                            equity = float(equity.replace(',', ''))
                                        except:
                                            continue
                                    if equity and equity > 0:
                                        shareholder_equity = equity
                                        shareholder_equity_quarterly.append({
                                            'year': fiscal_year,
                                            'quarter': fiscal_quarter,
                                            'shareholder_equity': equity,
                                            'fiscal_end': fiscal_end
                                        })
                                        break
                                
                                # Calculate Debt/Equity if both available
                                if total_debt is not None and shareholder_equity is not None and shareholder_equity > 0:
                                    debt_to_equity_quarterly.append({
                                        'year': fiscal_year,
                                        'quarter': fiscal_quarter,
                                        'debt_to_equity': total_debt / shareholder_equity,
                                        'fiscal_end': fiscal_end
                                    })
                                
                                # Extract Shares Outstanding
                                shares_rows = bs_df[bs_df['label'].str.contains('Shares', case=False, na=False) & 
                                                   bs_df['label'].str.contains('Outstanding', case=False, na=False)]
                                
                                for idx in range(len(shares_rows)):
                                    shares_row = shares_rows.iloc[idx]
                                    if 'abstract' in bs_df.columns and shares_row.get('abstract', False):
                                        continue
                                    shares = shares_row[quarterly_col]
                                    if isinstance(shares, str):
                                        if shares.strip() == '':
                                            continue
                                        try:
                                            shares = float(shares.replace(',', ''))
                                        except:
                                            continue
                                    if shares and shares > 0:
                                        shares_outstanding_quarterly.append({
                                            'year': fiscal_year,
                                            'quarter': fiscal_quarter,
                                            'shares': shares,
                                            'fiscal_end': fiscal_end
                                        })
                                        break
                    
                    # Extract from Cash Flow Statement
                    cashflow = statements.cashflow_statement()
                    if cashflow:
                        cf_df = cashflow.to_dataframe()
                        
                        if 'label' in cf_df.columns:
                            # Find quarterly column
                            quarterly_cols = [col for col in cf_df.columns if isinstance(col, str) and '(Q' in col]
                            
                            if quarterly_cols:
                                quarterly_col = quarterly_cols[0]
                                
                                # Extract Operating Cash Flow
                                ocf_rows = cf_df[cf_df['label'].str.contains('Operating', case=False, na=False) & 
                                                cf_df['label'].str.contains('Cash', case=False, na=False)]
                                
                                operating_cash_flow = None
                                for idx in range(len(ocf_rows)):
                                    ocf_row = ocf_rows.iloc[idx]
                                    if 'abstract' in cf_df.columns and ocf_row.get('abstract', False):
                                        continue
                                    ocf = ocf_row[quarterly_col]
                                    if isinstance(ocf, str):
                                        if ocf.strip() == '':
                                            continue
                                        try:
                                            ocf = float(ocf.replace(',', ''))
                                        except:
                                            continue
                                    if ocf is not None:
                                        operating_cash_flow = ocf
                                        break
                                
                                # Extract CapEx
                                capex_rows = cf_df[cf_df['label'].str.contains('Capital Expenditure', case=False, na=False) | 
                                                  cf_df['label'].str.contains('Property', case=False, na=False)]
                                
                                capital_expenditures = None
                                for idx in range(len(capex_rows)):
                                    capex_row = capex_rows.iloc[idx]
                                    if 'abstract' in cf_df.columns and capex_row.get('abstract', False):
                                        continue
                                    capex = capex_row[quarterly_col]
                                    if isinstance(capex, str):
                                        if capex.strip() == '':
                                            continue
                                        try:
                                            capex = float(capex.replace(',', ''))
                                        except:
                                            continue
                                    if capex is not None:
                                        # CapEx is usually negative in cash flow statement
                                        capital_expenditures = abs(capex)
                                        break
                                
                                # Calculate Free Cash Flow if both available
                                if operating_cash_flow is not None or capital_expenditures is not None:
                                    fcf = None
                                    if operating_cash_flow is not None and capital_expenditures is not None:
                                        fcf = operating_cash_flow - capital_expenditures
                                    
                                    cash_flow_quarterly.append({
                                        'year': fiscal_year,
                                        'quarter': fiscal_quarter,
                                        'operating_cash_flow': operating_cash_flow,
                                        'capital_expenditures': capital_expenditures,
                                        'free_cash_flow': fcf,
                                        'fiscal_end': fiscal_end
                                    })
                
                except Exception as e:
                    logger.debug(f"[{ticker}] Error processing filing {filing.filing_date}: {e}")
                    continue
            
            logger.info(f"[{ticker}] Extracted from 10-Q filings: {len(revenue_quarterly)} revenue, {len(eps_quarterly)} EPS, {len(net_income_quarterly)} NI, {len(cash_flow_quarterly)} CF, {len(debt_to_equity_quarterly)} D/E, {len(shares_outstanding_quarterly)} shares, {len(shareholder_equity_quarterly)} equity")
            
            return {
                'revenue_quarterly': revenue_quarterly,
                'eps_quarterly': eps_quarterly,
                'net_income_quarterly': net_income_quarterly,
                'cash_flow_quarterly': cash_flow_quarterly,
                'debt_to_equity_quarterly': debt_to_equity_quarterly,
                'shares_outstanding_quarterly': shares_outstanding_quarterly,
                'shareholder_equity_quarterly': shareholder_equity_quarterly
            }
        
        except Exception as e:
            logger.error(f"[{ticker}] Error in get_quarterly_financials_from_10q: {e}")
            import traceback
            traceback.print_exc()
            return {}
    def _fetch_fundamentals_from_db(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Reconstruct fundamentals from parsed earnings_history in DB.
        Bypasses raw company_facts fetch if we already have the data.
        """
        try:
            # Check for basic metrics first
            metrics = self.db.get_stock_metrics(ticker)
            if not metrics:
                return None
                
            # Get annual and quarterly history
            annual_rows = self.db.get_earnings_history(ticker, period_type='annual')
            quarterly_rows = self.db.get_earnings_history(ticker, period_type='quarterly')
            
            if not annual_rows:
                return None
            
            # Helper to map DB rows to dicts
            def map_rows(rows, val_key, out_key_val='val'):
                return [{
                    'year': r['year'],
                    'quarter': r.get('period') if r.get('period') not in ['annual', None] else None,
                    out_key_val: r.get(val_key),
                    'fiscal_end': r.get('fiscal_end')
                } for r in rows if r.get(val_key) is not None]

            # Reconstruct lists
            eps_history = [{
                'year': r['year'],
                'eps': r['eps'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('eps') is not None]
            
            revenue_history = [{
                'year': r['year'],
                'revenue': r['revenue'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('revenue') is not None]
            
            net_income_annual = [{
                'year': r['year'],
                'net_income': r['net_income'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('net_income') is not None]
            
            # Quarterly lists
            net_income_quarterly = map_rows(quarterly_rows, 'net_income', 'net_income')
            revenue_quarterly = map_rows(quarterly_rows, 'revenue', 'revenue')
            eps_quarterly = map_rows(quarterly_rows, 'eps', 'eps')
            cash_flow_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'operating_cash_flow': r['operating_cash_flow'],
                'capital_expenditures': r['capital_expenditures'],
                'free_cash_flow': r['free_cash_flow'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('operating_cash_flow') is not None]

            # Other annual histories
            cash_flow_history = [{
                'year': r['year'],
                'operating_cash_flow': r['operating_cash_flow'],
                'capital_expenditures': r['capital_expenditures'],
                'free_cash_flow': r['free_cash_flow'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('operating_cash_flow') is not None]

            debt_to_equity_history = [{
                'year': r['year'],
                'debt_to_equity': r['debt_to_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('debt_to_equity') is not None]
            
            debt_to_equity_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'debt_to_equity': r['debt_to_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('debt_to_equity') is not None]

            shareholder_equity_history = [{
                'year': r['year'],
                'shareholder_equity': r['shareholder_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('shareholder_equity') is not None]
            
            shareholder_equity_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'shareholder_equity': r['shareholder_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('shareholder_equity') is not None]

            shares_outstanding_history = [{
                'year': r['year'],
                'shares': r['shares_outstanding'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('shares_outstanding') is not None]
            
            shares_outstanding_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'shares': r['shares_outstanding'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('shares_outstanding') is not None]

            dividend_history = [{
                'year': r['year'],
                'amount': r['dividend_amount'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('dividend_amount') is not None]

            cash_equivalents_history = [{
                'year': r['year'],
                'cash_and_cash_equivalents': r['cash_and_cash_equivalents'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('cash_and_cash_equivalents') is not None]
            
            # Most recent debt_to_equity
            current_de = metrics.get('debt_to_equity')
            
            # CIK
            cik = self.get_cik_for_ticker(ticker)

            return {
                'ticker': ticker,
                'cik': cik,
                'company_name': metrics.get('company_name', ''),
                'eps_history': eps_history,
                'calculated_eps_history': eps_history, # Use same as reported
                'net_income_annual': net_income_annual,
                'shareholder_equity_history': shareholder_equity_history,
                'shareholder_equity_quarterly': shareholder_equity_quarterly,
                'cash_equivalents_history': cash_equivalents_history,
                'shares_outstanding_history': shares_outstanding_history,
                'net_income_quarterly': net_income_quarterly,
                'revenue_quarterly': revenue_quarterly,
                'eps_quarterly': eps_quarterly,
                'calculated_eps_quarterly': eps_quarterly,
                'cash_flow_quarterly': cash_flow_quarterly,
                'debt_to_equity_quarterly': debt_to_equity_quarterly,
                'shares_outstanding_quarterly': shares_outstanding_quarterly,
                'revenue_history': revenue_history,
                'debt_to_equity': current_de,
                'debt_to_equity_history': debt_to_equity_history,
                'cash_flow_history': cash_flow_history,
                'dividend_history': dividend_history,
                'interest_expense': metrics.get('interest_expense'),
                'effective_tax_rate': metrics.get('effective_tax_rate'),
                'company_facts': {} # Emulate empty raw data
            }

        except Exception as e:
            logger.warning(f"[{ticker}] Failed to reconstruct fundamentals from DB: {e}")
            return None


    def _needs_quarterly_refresh(self, ticker: str) -> bool:
        """
        Check if we need to refresh quarterly data from 10-Q filings.
        Returns True if the cached quarterly data is missing the most recent quarter.

        Args:
            ticker: Stock ticker symbol

        Returns:
            True if quarterly data needs refresh, False if cached data is current
        """
        if not self.db:
            return True  # No DB means we need to fetch

        try:
            from datetime import datetime, timedelta

            # Get most recent quarterly earnings from DB
            quarterly_rows = self.db.get_earnings_history(ticker, period_type='quarterly')
            if not quarterly_rows:
                logger.info(f"[{ticker}] No quarterly data in DB - needs refresh")
                return True

            # Find the most recent quarter in DB
            most_recent = max(quarterly_rows, key=lambda r: (r['year'], r.get('period', 'Q1')))
            db_year = most_recent['year']
            db_quarter = most_recent.get('period', 'Q1')  # e.g., 'Q1', 'Q2', 'Q3', 'Q4'
            db_quarter_num = int(db_quarter.replace('Q', ''))

            # Get fiscal year end from most recent annual data to determine fiscal calendar
            annual_rows = self.db.get_earnings_history(ticker, period_type='annual')
            if not annual_rows:
                logger.info(f"[{ticker}] No annual data to determine fiscal year end - needs refresh")
                return True

            # Get fiscal year end (e.g., '2024-12-31')
            most_recent_annual = max(annual_rows, key=lambda r: r['year'])
            fiscal_end_str = most_recent_annual.get('fiscal_end')
            if not fiscal_end_str:
                logger.info(f"[{ticker}] No fiscal_end date available - needs refresh")
                return True

            # Parse fiscal year end to get the month/day (e.g., Dec 31 -> 12-31)
            fiscal_end_date = datetime.strptime(fiscal_end_str, '%Y-%m-%d')
            fiscal_month = fiscal_end_date.month
            fiscal_day = fiscal_end_date.day

            # Calculate what the expected current quarter should be
            today = datetime.now()

            # Determine the current fiscal year based on fiscal year end
            if (today.month, today.day) >= (fiscal_month, fiscal_day):
                current_fiscal_year = today.year
            else:
                current_fiscal_year = today.year - 1

            # Calculate quarter end dates for this fiscal year
            # Fiscal Q4 ends on fiscal_end (e.g., Dec 31)
            # Fiscal Q3 ends 3 months before
            # Fiscal Q2 ends 6 months before
            # Fiscal Q1 ends 9 months before
            q4_end = datetime(current_fiscal_year, fiscal_month, fiscal_day)
            q3_end = q4_end - timedelta(days=90)  # Approximate
            q2_end = q3_end - timedelta(days=90)
            q1_end = q2_end - timedelta(days=90)

            # Determine which quarter we should have data for
            # Companies typically file 10-Q within 45 days after quarter end
            filing_delay = timedelta(days=45)

            if today >= q4_end + filing_delay:
                expected_quarter = 4
                expected_year = current_fiscal_year
            elif today >= q3_end + filing_delay:
                expected_quarter = 3
                expected_year = current_fiscal_year
            elif today >= q2_end + filing_delay:
                expected_quarter = 2
                expected_year = current_fiscal_year
            elif today >= q1_end + filing_delay:
                expected_quarter = 1
                expected_year = current_fiscal_year
            else:
                # We're before Q1 filing, so expect Q4 of previous fiscal year
                expected_quarter = 4
                expected_year = current_fiscal_year - 1

            # Check if we have the expected quarter in DB
            if db_year < expected_year or (db_year == expected_year and db_quarter_num < expected_quarter):
                logger.info(f"[{ticker}] Quarterly data stale: DB has {db_year} Q{db_quarter_num}, expected {expected_year} Q{expected_quarter} - needs refresh")
                return True

            logger.info(f"[{ticker}] Quarterly data current: DB has {db_year} Q{db_quarter_num}, expected {expected_year} Q{expected_quarter} - no refresh needed")
            return False

        except Exception as e:
            logger.warning(f"[{ticker}] Error checking quarterly freshness: {e} - will refresh to be safe")
            return True


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

        # Try to fetch from DB first (earnings_history)
        # This avoids redundant SEC API calls since company_facts table is unused
        has_cached_data = False
        db_fundamentals = None
        if self.db:
            db_fundamentals = self._fetch_fundamentals_from_db(ticker)
            if db_fundamentals:
                has_cached_data = True
                # We have cached data, but check if quarterly data needs updating
                needs_quarterly_refresh = self._needs_quarterly_refresh(ticker)
                if not needs_quarterly_refresh:
                    logger.info(f"[{ticker}] Returning fundamentals from earnings_history DB cache (quarterly data current)")
                    return db_fundamentals
                else:
                    logger.info(f"[{ticker}] DB cache exists but quarterly data is stale - will refresh recent quarters only")

        # Fetch company facts (skip if we have cached historical data and only need quarterly refresh)
        company_facts = None
        if not has_cached_data:
            company_facts = self.fetch_company_facts(cik)
            if not company_facts:
                return None

        # Parse all fundamental data (skip if using cached data)
        if not has_cached_data:
            eps_history = self.parse_eps_history(company_facts)
            revenue_history = self.parse_revenue_history(company_facts)
            debt_to_equity = self.parse_debt_to_equity(company_facts)
            debt_to_equity_history = self.parse_debt_to_equity_history(company_facts)
            shareholder_equity_history = self.parse_shareholder_equity_history(company_facts)
            # shareholder_equity_quarterly now comes from 10-Q parsing above
            cash_equivalents_history = self.parse_cash_equivalents_history(company_facts)
            cash_flow_history = self.parse_cash_flow_history(company_facts)

            # Extract Interest Expense and Tax Rate
            interest_expense = self.parse_interest_expense(company_facts)
            effective_tax_rate = self.parse_effective_tax_rate(company_facts)

            # Calculate split-adjusted EPS from Net Income / Shares Outstanding
            calculated_eps_history = self.calculate_split_adjusted_annual_eps_history(company_facts)

            # Extract Net Income directly for storage
            net_income_annual = self.parse_net_income_history(company_facts)
        else:
            # Use data from cached DB fundamentals
            logger.info(f"[{ticker}] Using historical data from DB cache, only refreshing quarterly")
            eps_history = db_fundamentals.get('eps_history', [])
            revenue_history = db_fundamentals.get('revenue_history', [])
            debt_to_equity = db_fundamentals.get('debt_to_equity')
            debt_to_equity_history = db_fundamentals.get('debt_to_equity_history', [])
            shareholder_equity_history = db_fundamentals.get('shareholder_equity_history', [])
            cash_equivalents_history = db_fundamentals.get('cash_equivalents_history', [])
            cash_flow_history = db_fundamentals.get('cash_flow_history', [])
            interest_expense = db_fundamentals.get('interest_expense')
            effective_tax_rate = db_fundamentals.get('effective_tax_rate')
            calculated_eps_history = db_fundamentals.get('calculated_eps_history', eps_history)
            net_income_annual = db_fundamentals.get('net_income_annual', [])
        
        
        # HYBRID APPROACH: Combine 10-Q parsing (accurate recent data) with company_facts (complete historical data)
        # - Use 10-Q parsing for last 8 quarters (most accurate, handles fiscal quarters correctly)
        # - Use company_facts for historical data (complete coverage, even if slightly outdated)
        logger.info(f"[{ticker}] Extracting quarterly data using hybrid approach...")
        
        # 1. Get recent quarters from 10-Q filings (last 8 quarters, ~2 years)
        logger.info(f"[{ticker}] Fetching recent 8 quarters from 10-Q filings...")
        quarterly_10q_data = self.get_quarterly_financials_from_10q(ticker, num_quarters=8)
        
        # NOTE: The cumulative revenue fix below was removed - the root cause was that
        # income = statements.income_statement() was not being called when fiscal info
        # was found from the cover page. This has been fixed above.
        

        # 2. Get historical quarters from company_facts (or from DB cache)
        if not has_cached_data:
            logger.info(f"[{ticker}] Fetching historical quarterly data from company_facts...")
            historical_revenue_quarterly = self.parse_quarterly_revenue_history(company_facts)
            historical_net_income_quarterly = self.parse_quarterly_net_income_history(company_facts)
            historical_cash_flow_quarterly = self.parse_quarterly_cash_flow_history(company_facts)
            historical_debt_to_equity_quarterly = self.parse_quarterly_debt_to_equity_history(company_facts)
            historical_shares_outstanding_quarterly = self.parse_quarterly_shares_outstanding_history(company_facts)
            historical_shareholder_equity_quarterly = self.parse_quarterly_shareholder_equity_history(company_facts)
        else:
            logger.info(f"[{ticker}] Using historical quarterly data from DB cache...")
            historical_revenue_quarterly = db_fundamentals.get('revenue_quarterly', [])
            historical_net_income_quarterly = db_fundamentals.get('net_income_quarterly', [])
            historical_cash_flow_quarterly = db_fundamentals.get('cash_flow_quarterly', [])
            historical_debt_to_equity_quarterly = db_fundamentals.get('debt_to_equity_quarterly', [])
            historical_shares_outstanding_quarterly = db_fundamentals.get('shares_outstanding_quarterly', [])
            historical_shareholder_equity_quarterly = db_fundamentals.get('shareholder_equity_quarterly', [])
        
        # 3. Merge: 10-Q data takes precedence for recent quarters
        def merge_quarterly_data(recent_data, historical_data):
            """Merge recent 10-Q data with historical company_facts data, 10-Q takes precedence"""
            # Create dict keyed by (year, quarter) for recent data
            recent_by_key = {(e['year'], e['quarter']): e for e in recent_data}
            
            # Create dict for historical data
            historical_by_key = {(e['year'], e['quarter']): e for e in historical_data}
            
            # Merge: start with historical, then overwrite with recent
            merged = dict(historical_by_key)
            merged.update(recent_by_key)
            
            # Convert back to list and sort by date (newest first)
            result = list(merged.values())
            result.sort(key=lambda x: (x['year'], x['quarter']), reverse=True)
            return result
        
        # Merge each metric
        revenue_quarterly = merge_quarterly_data(
            quarterly_10q_data.get('revenue_quarterly', []),
            historical_revenue_quarterly or []
        )
        
        net_income_quarterly = merge_quarterly_data(
            quarterly_10q_data.get('net_income_quarterly', []),
            historical_net_income_quarterly or []
        )
        
        eps_quarterly = quarterly_10q_data.get('eps_quarterly', [])  # Only from 10-Q (more accurate)
        
        cash_flow_quarterly = merge_quarterly_data(
            quarterly_10q_data.get('cash_flow_quarterly', []),
            historical_cash_flow_quarterly or []
        )
        
        debt_to_equity_quarterly = merge_quarterly_data(
            quarterly_10q_data.get('debt_to_equity_quarterly', []),
            historical_debt_to_equity_quarterly or []
        )
        
        shares_outstanding_quarterly = merge_quarterly_data(
            quarterly_10q_data.get('shares_outstanding_quarterly', []),
            historical_shares_outstanding_quarterly or []
        )
        
        shareholder_equity_quarterly = merge_quarterly_data(
            quarterly_10q_data.get('shareholder_equity_quarterly', []),
            historical_shareholder_equity_quarterly or []
        )
        
        logger.info(f"[{ticker}] Hybrid merge complete: {len(revenue_quarterly)} revenue quarters, {len(net_income_quarterly)} NI quarters, {len(eps_quarterly)} EPS quarters")
        
        # Keep calculated EPS from company_facts as fallback
        calculated_eps_quarterly = self.calculate_quarterly_eps_history(company_facts)

        # Extract shares outstanding history (annual)
        shares_outstanding_history = self.parse_shares_outstanding_history(company_facts)

        # Parse dividend history
        dividend_history = self.parse_dividend_history(company_facts)

        logger.info(f"[{ticker}] EDGAR fetch complete: {len(eps_history or [])} EPS years, {len(calculated_eps_history or [])} calculated EPS years, {len(net_income_annual or [])} annual NI, {len(net_income_quarterly or [])} quarterly NI, {len(revenue_quarterly or [])} quarterly Rev, {len(eps_quarterly or [])} quarterly EPS, {len(calculated_eps_quarterly or [])} calculated Q-EPS, {len(cash_flow_quarterly or [])} quarterly CF, {len(revenue_history or [])} revenue years, {len(debt_to_equity_history or [])} D/E years, {len(debt_to_equity_quarterly)} quarterly D/E, {len(shareholder_equity_history or [])} Equity years, {len(shareholder_equity_quarterly)} Quarterly Equity, {len(cash_equivalents_history or [])} Cash years, {len(shares_outstanding_history or [])} shares outstanding years, {len(cash_flow_history or [])} cash flow years, {len(dividend_history or [])} dividend entries, current D/E: {debt_to_equity}")

        fundamentals = {
            'ticker': ticker,
            'cik': cik,
            'company_name': company_facts.get('entityName', ''),
            'eps_history': eps_history,
            'calculated_eps_history': calculated_eps_history,
            'net_income_annual': net_income_annual,
            'shareholder_equity_history': shareholder_equity_history,
            'shareholder_equity_quarterly': shareholder_equity_quarterly,
            'cash_equivalents_history': cash_equivalents_history,
            'shares_outstanding_history': shares_outstanding_history,
            'net_income_quarterly': net_income_quarterly,
            'revenue_quarterly': revenue_quarterly,
            'eps_quarterly': eps_quarterly,
            'calculated_eps_quarterly': calculated_eps_quarterly,
            'cash_flow_quarterly': cash_flow_quarterly,
            'debt_to_equity_quarterly': debt_to_equity_quarterly,
            'shares_outstanding_quarterly': shares_outstanding_quarterly,
            'revenue_history': revenue_history,
            'debt_to_equity': debt_to_equity,
            'debt_to_equity_history': debt_to_equity_history,
            'cash_flow_history': cash_flow_history,
            'dividend_history': dividend_history,
            'interest_expense': interest_expense,
            'effective_tax_rate': effective_tax_rate,
            'company_facts': company_facts
        }

        return fundamentals


    def fetch_recent_filings(self, ticker: str, since_date: str = None) -> List[Dict[str, Any]]:
        """
        Fetch recent 10-K and 10-Q filings for a ticker

        Args:
            ticker: Stock ticker symbol
            since_date: Optional date string (YYYY-MM-DD) to filter filings newer than this date

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
                if form in ['10-K', '10-Q', '20-F', '6-K']:
                    filing_date = filing_dates[i]
                    
                    # Skip filings older than since_date (incremental fetch)
                    if since_date and filing_date <= since_date:
                        continue
                    
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
                        'date': filing_date,
                        'url': doc_url,
                        'accession_number': acc_num
                    })

            if since_date and not filings:
                logger.debug(f"[SECDataFetcher][{ticker}] No new SEC filings since {since_date}")
            else:
                logger.info(f"[SECDataFetcher][{ticker}] Found {len(filings)} SEC filings" + 
                           (f" (new since {since_date})" if since_date else ""))
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
        import time
        t_start = time.time()
        
        logger.info(f"[SECDataFetcher][{ticker}] Extracting sections from {filing_type} using edgartools")
        sections = {}

        try:
            # Get CIK first to avoid edgartools ticker lookup issues
            t0 = time.time()
            cik = self.get_cik_for_ticker(ticker)
            t_cik = (time.time() - t0) * 1000
            
            if not cik:
                logger.warning(f"[SECDataFetcher][{ticker}] Could not find CIK for section extraction")
                return {}

            # Get company using cached Company object (avoids redundant SEC calls)
            t0 = time.time()
            company = self.get_company(cik)
            t_company = (time.time() - t0) * 1000
            
            if not company:
                logger.warning(f"[SECDataFetcher][{ticker}] Could not get Company object")
                return {}
            
            # Get filings list
            t0 = time.time()
            filings = company.get_filings(form=filing_type)
            t_get_filings = (time.time() - t0) * 1000

            if not filings:
                logger.warning(f"[SECDataFetcher][{ticker}] No {filing_type} filings found")
                return {}

            t0 = time.time()
            latest_filing = filings.latest()
            filing_date = str(latest_filing.filing_date)
            t_latest = (time.time() - t0) * 1000
            logger.info(f"[SECDataFetcher][{ticker}] Found {filing_type} filing from {filing_date}")

            # Get the structured filing object - THIS IS THE EXPENSIVE PART
            t0 = time.time()
            filing_obj = latest_filing.obj()
            t_obj = (time.time() - t0) * 1000

            # Extract sections
            t0 = time.time()
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

            elif filing_type == '20-F':
                # Extract 20-F sections (Foreign Private Issuer Annual Report)
                # 20-F item numbering differs from 10-K:
                # Item 4 = Information on the Company (equivalent to Item 1 Business)
                # Item 3D = Risk Factors (equivalent to Item 1A)
                # Item 5 = Operating and Financial Review (equivalent to Item 7 MD&A)
                # Item 11 = Quantitative and Qualitative Disclosures (equivalent to Item 7A)
                
                try:
                    business = filing_obj["Item 4"]
                    if business:
                        sections['business'] = {
                            'content': business,
                            'filing_type': '20-F',
                            'filing_date': filing_date
                        }
                        logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 4 (Business): {len(str(business))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[SECDataFetcher][{ticker}] Item 4 (Business) not available in 20-F")

                try:
                    risk_factors = filing_obj["Item 3D"]
                    if risk_factors:
                        sections['risk_factors'] = {
                            'content': risk_factors,
                            'filing_type': '20-F',
                            'filing_date': filing_date
                        }
                        logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 3D (Risk Factors): {len(str(risk_factors))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[SECDataFetcher][{ticker}] Item 3D (Risk Factors) not available in 20-F")

                try:
                    mda = filing_obj["Item 5"]
                    if mda:
                        sections['mda'] = {
                            'content': mda,
                            'filing_type': '20-F',
                            'filing_date': filing_date
                        }
                        logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 5 (MD&A): {len(str(mda))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[SECDataFetcher][{ticker}] Item 5 (MD&A) not available in 20-F")

                try:
                    market_risk = filing_obj["Item 11"]
                    if market_risk:
                        sections['market_risk'] = {
                            'content': market_risk,
                            'filing_type': '20-F',
                            'filing_date': filing_date
                        }
                        logger.info(f"[SECDataFetcher][{ticker}] Extracted Item 11 (Market Risk): {len(str(market_risk))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[SECDataFetcher][{ticker}] Item 11 (Market Risk) not available in 20-F")

            t_extract = (time.time() - t0) * 1000
            t_total = (time.time() - t_start) * 1000
            
            # Detailed timing log for extract_filing_sections
            logger.info(f"[{ticker}] extract_{filing_type}: cik={t_cik:.0f}ms company={t_company:.0f}ms get_filings={t_get_filings:.0f}ms latest={t_latest:.0f}ms OBJ={t_obj:.0f}ms extract={t_extract:.0f}ms TOTAL={t_total:.0f}ms")
            
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

    def fetch_form4_filings(self, ticker: str, since_date: str = None) -> List[Dict[str, Any]]:
        """
        Fetch Form 4 insider transaction filings and parse transaction details.
        
        Form 4 filings contain detailed insider transaction information including:
        - Transaction codes (P=Purchase, S=Sale, M=Exercise, A=Award, F=Tax, G=Gift)
        - 10b5-1 plan indicators
        - Direct vs indirect ownership
        - Owner relationship (Officer, Director, 10% owner)
        
        Args:
            ticker: Stock ticker symbol
            since_date: Optional date string (YYYY-MM-DD) to filter filings newer than this date
                       Defaults to 1 year ago if not specified
        
        Returns:
            List of transaction dicts with enriched insider data
        """
        from datetime import datetime, timedelta
        import xml.etree.ElementTree as ET
        
        cik = self.get_cik_for_ticker(ticker)
        if not cik:
            logger.warning(f"[{ticker}] Could not find CIK for Form 4 fetch")
            return []
        
        # Default to 1 year back if no since_date specified
        if not since_date:
            one_year_ago = datetime.now() - timedelta(days=365)
            since_date = one_year_ago.strftime('%Y-%m-%d')
        
        padded_cik = cik.zfill(10)
        
        try:
            self._rate_limit(caller=f"form4-submissions-{ticker}")
            submissions_url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
            response = requests.get(submissions_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            recent_filings = data.get('filings', {}).get('recent', {})
            
            if not recent_filings:
                logger.debug(f"[{ticker}] No recent filings found for Form 4")
                return []
            
            forms = recent_filings.get('form', [])
            filing_dates = recent_filings.get('filingDate', [])
            accession_numbers = recent_filings.get('accessionNumber', [])
            primary_documents = recent_filings.get('primaryDocument', [])
            
            # Collect Form 4 filing URLs
            form4_filings = []
            for i, form in enumerate(forms):
                if form == '4':
                    filing_date = filing_dates[i]
                    
                    # Skip filings older than since_date
                    if since_date and filing_date < since_date:
                        continue
                    
                    acc_num = accession_numbers[i]
                    acc_num_no_dashes = acc_num.replace('-', '')
                    primary_doc = primary_documents[i] if i < len(primary_documents) else None
                    
                    if primary_doc and primary_doc.endswith('.xml'):
                        # Important: primary_doc often includes xsl directory (e.g. xslF345X03/doc.xml)
                        # The raw XML is always in the root (e.g. doc.xml)
                        # The xsl path returns the rendered HTML!
                        primary_doc_basename = primary_doc.split('/')[-1]
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_no_dashes}/{primary_doc_basename}"
                    else:
                        # Fallback for non-xml primary docs (unlikely for Form 4)
                        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_no_dashes}/{primary_doc}"
                    
                    form4_filings.append({
                        'filing_date': filing_date,
                        'accession_number': acc_num,
                        'url': doc_url
                    })
            
            logger.info(f"[{ticker}] Found {len(form4_filings)} Form 4 filings since {since_date}")
            
            # Parse each Form 4 XML for transaction details
            all_transactions = []
            for filing in form4_filings:
                try:
                    transactions = self._parse_form4_filing(ticker, filing, cik)
                    all_transactions.extend(transactions)
                except Exception as e:
                    logger.debug(f"[{ticker}] Error parsing Form 4 {filing['accession_number']}: {e}")
            
            logger.info(f"[{ticker}] Extracted {len(all_transactions)} transactions from Form 4 filings")
            return all_transactions
            
        except Exception as e:
            logger.error(f"[{ticker}] Error fetching Form 4 filings: {e}")
            return []
    
    def _parse_form4_filing(self, ticker: str, filing: Dict[str, Any], cik: str) -> List[Dict[str, Any]]:
        """
        Parse a single Form 4 XML filing to extract transaction details.
        
        Form 4 XML structure (simplified):
        <ownershipDocument>
            <reportingOwner>
                <reportingOwnerId>
                    <rptOwnerName>John Smith</rptOwnerName>
                </reportingOwnerId>
                <reportingOwnerRelationship>
                    <isDirector>true</isDirector>
                    <isOfficer>true</isOfficer>
                    <officerTitle>CEO</officerTitle>
                </reportingOwnerRelationship>
            </reportingOwner>
            <nonDerivativeTable>
                <nonDerivativeTransaction>
                    <transactionDate><value>2024-01-15</value></transactionDate>
                    <transactionCoding>
                        <transactionCode>P</transactionCode>  <!-- P=Purchase, S=Sale, M=Exercise, A=Award, F=Tax, G=Gift -->
                    </transactionCoding>
                    <transactionAmounts>
                        <transactionShares><value>1000</value></transactionShares>
                        <transactionPricePerShare><value>50.00</value></transactionPricePerShare>
                    </transactionAmounts>
                    <ownershipNature>
                        <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
                    </ownershipNature>
                </nonDerivativeTransaction>
            </nonDerivativeTable>
        </ownershipDocument>
        
        Args:
            ticker: Stock ticker symbol
            filing: Filing dict with url, filing_date, accession_number
            cik: Company CIK
            
        Returns:
            List of transaction dicts
        """
        import xml.etree.ElementTree as ET
        
        self._rate_limit(caller=f"form4-xml-{ticker}")
        
        # Try to fetch the XML
        url = filing['url']
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
        except Exception as e:
            # If primary doc fails, try common Form 4 XML patterns
            acc_num_no_dashes = filing['accession_number'].replace('-', '')
            alt_urls = [
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_no_dashes}/form4.xml",
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_no_dashes}/primary_doc.xml",
            ]
            
            response = None
            for alt_url in alt_urls:
                try:
                    self._rate_limit(caller=f"form4-xml-alt-{ticker}")
                    response = requests.get(alt_url, headers=self.headers, timeout=10)
                    if response.status_code == 200:
                        break
                except Exception:
                    continue
            
            if not response or response.status_code != 200:
                logger.debug(f"[{ticker}] Could not fetch Form 4 XML: {filing['accession_number']}")
                return []
        
        # Parse XML
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            logger.debug(f"[{ticker}] XML parse error: {e}. URL: {url}")
            return []
        
        # Define namespace (Form 4 XML may use namespaces)
        # Try with and without namespace
        ns = {}
        
        # Extract owner information
        owner_name = "Unknown"
        owner_relationship = "Other"
        officer_title = ""
        
        # Try to find reporting owner
        owner_elem = root.find('.//reportingOwner') or root.find('.//{*}reportingOwner')
        if owner_elem is not None:
            name_elem = owner_elem.find('.//rptOwnerName') or owner_elem.find('.//{*}rptOwnerName')
            if name_elem is not None and name_elem.text:
                owner_name = name_elem.text.strip()
            
            # Determine relationship
            rel_elem = owner_elem.find('.//reportingOwnerRelationship') or owner_elem.find('.//{*}reportingOwnerRelationship')
            if rel_elem is not None:
                is_director = (rel_elem.find('.//isDirector') or rel_elem.find('.//{*}isDirector'))
                is_officer = (rel_elem.find('.//isOfficer') or rel_elem.find('.//{*}isOfficer'))
                is_ten_percent = (rel_elem.find('.//isTenPercentOwner') or rel_elem.find('.//{*}isTenPercentOwner'))
                title_elem = (rel_elem.find('.//officerTitle') or rel_elem.find('.//{*}officerTitle'))
                
                relationships = []
                if is_director is not None and is_director.text and is_director.text.lower() in ['true', '1']:
                    relationships.append('Director')
                if is_officer is not None and is_officer.text and is_officer.text.lower() in ['true', '1']:
                    relationships.append('Officer')
                if is_ten_percent is not None and is_ten_percent.text and is_ten_percent.text.lower() in ['true', '1']:
                    relationships.append('10% Owner')
                
                if relationships:
                    owner_relationship = ', '.join(relationships)
                
                if title_elem is not None and title_elem.text:
                    officer_title = title_elem.text.strip()
        
        transactions = []
        
        # Extract all footnotes from the filing
        # Footnotes are typically in <footnotes><footnote id="F1">text</footnote></footnotes>
        footnotes_dict = {}
        footnotes_elem = root.find('.//footnotes') or root.find('.//{*}footnotes')
        if footnotes_elem is not None:
            for footnote in footnotes_elem.findall('.//footnote') + footnotes_elem.findall('.//{*}footnote'):
                fn_id = footnote.get('id', '')
                fn_text = footnote.text.strip() if footnote.text else ''
                if fn_id and fn_text:
                    footnotes_dict[fn_id] = fn_text
        
        # Parse non-derivative transactions (common stock)
        nd_table = root.find('.//nonDerivativeTable') or root.find('.//{*}nonDerivativeTable')
        if nd_table is not None:
            for tx in nd_table.findall('.//nonDerivativeTransaction') + nd_table.findall('.//{*}nonDerivativeTransaction'):
                tx_data = self._extract_transaction_data(tx, owner_name, owner_relationship, officer_title, filing, footnotes_dict=footnotes_dict)
                if tx_data:
                    transactions.append(tx_data)
        
        # Parse derivative transactions (options, warrants)
        d_table = root.find('.//derivativeTable') or root.find('.//{*}derivativeTable')
        if d_table is not None:
             for tx in d_table.findall('.//derivativeTransaction') + d_table.findall('.//{*}derivativeTransaction'):
                tx_data = self._extract_transaction_data(tx, owner_name, owner_relationship, officer_title, filing, is_derivative=True, footnotes_dict=footnotes_dict)
                if tx_data:
                    transactions.append(tx_data)
        
        return transactions
    
    def _extract_transaction_data(self, tx_elem, owner_name: str, owner_relationship: str, 
                                   officer_title: str, filing: Dict[str, Any], 
                                   is_derivative: bool = False, footnotes_dict: Dict[str, str] = None) -> Optional[Dict[str, Any]]:
        """
        Extract transaction data from a Form 4 transaction XML element.
        
        Transaction codes:
            P - Open market or private purchase
            S - Open market or private sale
            M - Exercise of derivative security (option exercise)
            A - Grant, award, or other acquisition
            F - Payment of exercise price or tax liability by delivering or withholding securities
            G - Gift of securities
            D - Disposition to the issuer
            J - Other acquisition or disposition
        
        Args:
            tx_elem: XML element for transaction
            owner_name: Name of the insider
            owner_relationship: Relationship to company
            officer_title: Title if officer
            filing: Filing metadata dict
            is_derivative: Whether this is a derivative transaction
            
        Returns:
            Transaction dict or None if extraction fails
        """
        def get_value(elem, *paths):
            """Helper to extract value from nested XML paths.
            
            SEC Form 4 XML typically has structure like:
            <transactionDate>
                <value>2025-01-15</value>
            </transactionDate>
            """
            for path in paths:
                # Try direct child first, then descendant
                found = elem.find(path)
                if found is None:
                    found = elem.find(f'.//{path}')
                if found is None:
                    found = elem.find(f'{{*}}{path}')  # With any namespace
                if found is None:
                    found = elem.find(f'.//{{*}}{path}')
                
                if found is not None:
                    # Try to find <value> child element (SEC standard structure)
                    val_elem = found.find('value')
                    if val_elem is None:
                        val_elem = found.find('{*}value')
                    if val_elem is None:
                        val_elem = found.find('.//value')
                    if val_elem is None:
                        val_elem = found.find('.//{*}value')
                    
                    # If no value child, use the element itself
                    if val_elem is None:
                        val_elem = found
                    
                    # Extract text
                    if val_elem is not None:
                        text = val_elem.text
                        if text and text.strip():
                            return text.strip()
            return None
        
        # Get transaction date
        tx_date = get_value(tx_elem, 'transactionDate')
        if not tx_date:
            return None
        
        # Normalize date format - SEC XML sometimes includes timezone offset (e.g., "2025-01-13-05:00")
        # Strip anything after the YYYY-MM-DD to get a clean date for PostgreSQL
        if len(tx_date) > 10 and tx_date[10] in ['-', '+', 'T']:
            tx_date = tx_date[:10]
        
        # Get transaction code
        tx_code = get_value(tx_elem, 'transactionCode')
        if not tx_code:
            # Check transactionCoding element
            coding_elem = tx_elem.find('.//transactionCoding') or tx_elem.find('.//{*}transactionCoding')
            if coding_elem is not None:
                code_elem = coding_elem.find('.//transactionCode') or coding_elem.find('.//{*}transactionCode')
                if code_elem is not None and code_elem.text:
                    tx_code = code_elem.text.strip()
        
        if not tx_code:
            tx_code = 'M' if is_derivative else 'P'  # Default based on transaction type
        
        # Get shares
        shares_str = get_value(tx_elem, 'transactionShares', 'shares')
        shares = float(shares_str) if shares_str else 0
        
        # Get price per share
        price_str = get_value(tx_elem, 'transactionPricePerShare', 'pricePerShare')
        price = float(price_str) if price_str else 0
        
        # Calculate value
        value = shares * price if shares and price else 0
        
        # Get acquisition/disposition flag
        acq_disp = get_value(tx_elem, 'acquisitionDispositionCode', 'transactionAcquiredDisposedCode')
        
        # Get direct/indirect ownership
        direct_indirect = get_value(tx_elem, 'directOrIndirectOwnership')
        if not direct_indirect:
            nature_elem = tx_elem.find('.//ownershipNature') or tx_elem.find('.//{*}ownershipNature')
            if nature_elem is not None:
                di_elem = nature_elem.find('.//directOrIndirectOwnership') or nature_elem.find('.//{*}directOrIndirectOwnership')
                if di_elem is not None:
                    val_elem = di_elem.find('.//value') or di_elem.find('.//{*}value') or di_elem
                    if val_elem is not None and val_elem.text:
                        direct_indirect = val_elem.text.strip()
        
        direct_indirect = direct_indirect or 'D'  # Default to direct
        
        # Get post-transaction shares owned
        # This tells us how many shares the insider owns AFTER this transaction
        shares_owned_after = None
        post_amounts = tx_elem.find('.//postTransactionAmounts')
        if post_amounts is None:
            post_amounts = tx_elem.find('.//{*}postTransactionAmounts')
        if post_amounts is not None:
            shares_after_elem = post_amounts.find('.//sharesOwnedFollowingTransaction')
            if shares_after_elem is None:
                shares_after_elem = post_amounts.find('.//{*}sharesOwnedFollowingTransaction')
            if shares_after_elem is not None:
                # Find the value child element
                # NOTE: Can't use 'or' operator because empty elements evaluate to False
                val_elem = shares_after_elem.find('value')
                if val_elem is None:
                    val_elem = shares_after_elem.find('{*}value')
                if val_elem is None:
                    val_elem = shares_after_elem.find('.//value')
                if val_elem is None:
                    val_elem = shares_after_elem.find('.//{*}value')
                
                # Get text from value element, or from parent as fallback
                text = None
                if val_elem is not None and val_elem.text:
                    text = val_elem.text.strip()
                elif shares_after_elem.text and shares_after_elem.text.strip():
                    text = shares_after_elem.text.strip()
                
                if text:
                    try:
                        shares_owned_after = float(text)
                    except (ValueError, TypeError):
                        pass
        
        # Calculate ownership percentage change
        # For sales: % sold = shares / (shares_after + shares) * 100
        # For purchases: % increase = shares / shares_after * 100 (if shares_after > 0)
        ownership_change_pct = None
        if shares_owned_after is not None and shares > 0:
            if acq_disp == 'D':  # Disposition (sale)
                # shares_before = shares_owned_after + shares
                shares_before = shares_owned_after + shares
                if shares_before > 0:
                    ownership_change_pct = round((shares / shares_before) * 100, 1)
            else:  # Acquisition (purchase)
                # After purchase, they own shares_owned_after, so before they had shares_owned_after - shares
                # But for purchases, we show what % of current holdings this represents
                if shares_owned_after > 0:
                    ownership_change_pct = round((shares / shares_owned_after) * 100, 1)
        
        # Check for 10b5-1 plan indicator
        # This can appear in footnotes or as a specific element
        is_10b51 = False
        
        # Check footnotes for 10b5-1 mentions
        for footnote in tx_elem.findall('.//footnoteId') + tx_elem.findall('.//{*}footnoteId'):
            footnote_id = footnote.get('id', '')
            # 10b5-1 is often in footnote references
            if '10b5' in footnote_id.lower() or 'rule' in footnote_id.lower():
                is_10b51 = True
                break
        
        # Also check for transactionTimeliness element (indicates pre-planned)
        timeliness = get_value(tx_elem, 'transactionTimeliness')
        if timeliness and timeliness.upper() == 'E':  # E = Early (pre-planned under 10b5-1)
            is_10b51 = True
        
        # Collect footnote texts for this transaction
        footnote_texts = []
        if footnotes_dict:
            for fn_ref in tx_elem.findall('.//footnoteId') + tx_elem.findall('.//{*}footnoteId'):
                fn_id = fn_ref.get('id', '')
                if fn_id and fn_id in footnotes_dict:
                    fn_text = footnotes_dict[fn_id]
                    if fn_text and fn_text not in footnote_texts:
                        footnote_texts.append(fn_text)
                        # Also check footnote text for 10b5-1 mentions
                        if '10b5-1' in fn_text.lower() or '10b-5' in fn_text.lower():
                            is_10b51 = True
        
        # Map transaction code to human-readable type
        code_to_type = {
            'P': 'Open Market Purchase',
            'S': 'Open Market Sale', 
            'M': 'Option Exercise',
            'A': 'Award/Grant',
            'F': 'Tax Withholding',
            'G': 'Gift',
            'D': 'Disposition',
            'J': 'Other',
            'C': 'Conversion',
            'E': 'Expiration',
            'H': 'Expiration (short)',
            'I': 'Discretionary',
            'L': 'Small Acquisition',
            'O': 'Exercise OTC',
            'U': 'Tender',
            'W': 'Acquisition/Disposition by Will',
            'X': 'Exercise In-the-Money',
            'Z': 'Deposit',
        }
        
        transaction_type_label = code_to_type.get(tx_code.upper(), 'Other')
        
        # Determine simplified buy/sell classification for aggregation
        # P = Buy, S/F = Sell, M/A/G/etc. = Other
        if tx_code.upper() == 'P':
            simple_type = 'Buy'
        elif tx_code.upper() in ['S', 'F', 'D']:
            simple_type = 'Sell'
        else:
            simple_type = 'Other'
        
        position = officer_title if officer_title else owner_relationship
        
        return {
            'name': owner_name,
            'position': position,
            'transaction_date': tx_date,
            'transaction_type': simple_type,  # Buy/Sell/Other for compatibility
            'transaction_code': tx_code.upper(),  # P/S/M/A/F/G etc.
            'transaction_type_label': transaction_type_label,  # Human-readable
            'shares': shares,
            'value': value,
            'price_per_share': price,
            'direct_indirect': direct_indirect,  # D=Direct, I=Indirect
            'acquisition_disposition': acq_disp,  # A=Acquisition, D=Disposition
            'shares_owned_after': shares_owned_after,  # Shares owned after transaction
            'ownership_change_pct': ownership_change_pct,  # % of holdings this represents
            'is_10b51_plan': is_10b51,
            'is_derivative': is_derivative,
            'footnotes': footnote_texts,  # List of footnote texts for this transaction
            'filing_url': f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={filing['accession_number'].split('-')[0]}&type=4",
            'filing_date': filing['filing_date'],
            'accession_number': filing['accession_number']
        }
