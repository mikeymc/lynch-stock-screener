# ABOUTME: Fetches financial data from SEC EDGAR API using CIK lookups
# ABOUTME: Provides historical EPS, revenue, and debt metrics from 10-K filings

import requests
import time
import logging
from typing import Dict, List, Optional, Any
from edgar import Company, set_identity

logger = logging.getLogger(__name__)


class EdgarFetcher:
    """Fetches stock fundamentals from SEC EDGAR database"""

    BASE_URL = "https://data.sec.gov"
    TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
    COMPANY_FACTS_URL = f"{BASE_URL}/api/xbrl/companyfacts/CIK{{cik}}.json"

    def __init__(self, user_agent: str):
        """
        Initialize EDGAR fetcher with required User-Agent header

        Args:
            user_agent: User-Agent string in format "Company Name email@example.com"
        """
        self.user_agent = user_agent
        self.headers = {
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate'
        }
        self.ticker_to_cik_cache = None
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 10 requests per second max

        # Set identity for edgartools
        set_identity(user_agent)

    def _rate_limit(self):
        """Enforce rate limiting of 10 requests per second"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _load_ticker_to_cik_mapping(self) -> Dict[str, str]:
        """Load ticker-to-CIK mapping from SEC"""
        if self.ticker_to_cik_cache is not None:
            return self.ticker_to_cik_cache

        try:
            self._rate_limit()
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
            logger.info(f"[{ticker}] Found CIK: {cik}")
        else:
            logger.warning(f"[{ticker}] CIK not found in EDGAR mapping")
        return cik

    def fetch_company_facts(self, cik: str) -> Optional[Dict[str, Any]]:
        """
        Fetch company facts from SEC EDGAR API

        Args:
            cik: 10-digit CIK number

        Returns:
            Dictionary containing company facts data or None on error
        """
        self._rate_limit()

        url = self.COMPANY_FACTS_URL.format(cik=cik)
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            logger.info(f"[CIK {cik}] Successfully fetched company facts from EDGAR")
            return response.json()
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
            logger.warning("Could not parse EPS history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Filter for annual reports (10-K for US, 20-F for foreign)
        annual_eps = []
        seen_years = set()

        for entry in eps_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                year = entry.get('fy')
                eps = entry.get('val')
                fiscal_end = entry.get('end')

                # Avoid duplicates, keep only one entry per fiscal year
                if year and eps and year not in seen_years:
                    annual_eps.append({
                        'year': year,
                        'eps': eps,
                        'fiscal_end': fiscal_end
                    })
                    seen_years.add(year)

        # Sort by year descending
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
            logger.warning("Could not parse quarterly EPS history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Filter for quarterly reports (10-Q for US, 6-K for foreign)
        quarterly_eps = []
        seen_quarters = set()

        for entry in eps_data_list:
            if entry.get('form') in ['10-Q', '6-K']:
                year = entry.get('fy')
                quarter = entry.get('fp')  # Fiscal period: Q1, Q2, Q3
                eps = entry.get('val')
                fiscal_end = entry.get('end')

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
            logger.warning("Could not parse Net Income history from EDGAR: No us-gaap or ifrs-full data found")
            return []

        # Filter for annual reports (10-K for US, 20-F for foreign)
        annual_net_income = []
        seen_years = set()

        for entry in net_income_data_list:
            if entry.get('form') in ['10-K', '20-F']:
                year = entry.get('fy')
                net_income = entry.get('val')
                fiscal_end = entry.get('end')

                # Avoid duplicates, keep only one entry per fiscal year
                if year and net_income is not None and year not in seen_years:
                    annual_net_income.append({
                        'year': year,
                        'net_income': net_income,
                        'fiscal_end': fiscal_end
                    })
                    seen_years.add(year)

        # Sort by year descending
        annual_net_income.sort(key=lambda x: x['year'], reverse=True)
        logger.info(f"Successfully parsed {len(annual_net_income)} years of Net Income data from EDGAR")
        return annual_net_income

    def parse_revenue_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract revenue history from company facts (supports both US-GAAP and IFRS)

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, revenue, and fiscal_end values
        """
        annual_revenue = []
        seen_years = set()
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
                            year = entry.get('fy')
                            revenue = entry.get('val')
                            fiscal_end = entry.get('end')

                            # Avoid duplicates across all fields
                            if year and revenue and year not in seen_years:
                                annual_revenue.append({
                                    'year': year,
                                    'revenue': revenue,
                                    'fiscal_end': fiscal_end
                                })
                                seen_years.add(year)

                except KeyError:
                    logger.debug(f"Revenue field '{field}' not found, trying next...")
                    continue

        except (KeyError, TypeError):
            pass

        # Fall back to IFRS if no US-GAAP data found (foreign companies filing 20-F)
        if not annual_revenue:
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
                                    year = entry.get('fy')
                                    revenue = entry.get('val')
                                    fiscal_end = entry.get('end')

                                    # Avoid duplicates
                                    if year and revenue and year not in seen_years:
                                        annual_revenue.append({
                                            'year': year,
                                            'revenue': revenue,
                                            'fiscal_end': fiscal_end
                                        })
                                        seen_years.add(year)

                    except KeyError:
                        logger.debug(f"IFRS revenue field '{field}' not found, trying next...")
                        continue

            except (KeyError, TypeError):
                pass

        if not annual_revenue:
            logger.warning(f"No revenue data found in us-gaap or ifrs-full")
            return []

        # Sort by year descending
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

            # Get most recent liabilities value
            liabilities_data = facts.get('Liabilities', {}).get('units', {}).get('USD', [])
            if not liabilities_data:
                return None

            liabilities_entries = [e for e in liabilities_data if e.get('form') == '10-K']
            if not liabilities_entries:
                return None

            liabilities_entries.sort(key=lambda x: x.get('end', ''), reverse=True)
            liabilities = liabilities_entries[0].get('val')

            if equity and liabilities and equity > 0:
                return liabilities / equity

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

            # Get equity data
            equity_data = facts.get('StockholdersEquity', {}).get('units', {}).get('USD', [])
            if not equity_data:
                logger.warning("No StockholdersEquity data found")
                return []

            # Get liabilities data
            liabilities_data = facts.get('Liabilities', {}).get('units', {}).get('USD', [])
            if not liabilities_data:
                logger.warning("No Liabilities data found")
                return []

            # Filter for 10-K entries and create lookup by fiscal year
            equity_by_year = {}
            for entry in equity_data:
                if entry.get('form') == '10-K':
                    year = entry.get('fy')
                    fiscal_end = entry.get('end')
                    val = entry.get('val')
                    if year and val and year not in equity_by_year:
                        equity_by_year[year] = {'val': val, 'fiscal_end': fiscal_end}

            liabilities_by_year = {}
            for entry in liabilities_data:
                if entry.get('form') == '10-K':
                    year = entry.get('fy')
                    fiscal_end = entry.get('end')
                    val = entry.get('val')
                    if year and val and year not in liabilities_by_year:
                        liabilities_by_year[year] = {'val': val, 'fiscal_end': fiscal_end}

            # Calculate D/E ratio for each year where we have both values
            debt_to_equity_history = []
            for year in equity_by_year.keys():
                if year in liabilities_by_year:
                    equity = equity_by_year[year]['val']
                    liabilities = liabilities_by_year[year]['val']
                    fiscal_end = equity_by_year[year]['fiscal_end']

                    if equity > 0:
                        debt_to_equity = liabilities / equity
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

        logger.info(f"[{ticker}] EDGAR fetch complete: {len(eps_history)} EPS years, {len(revenue_history)} revenue years, {len(debt_to_equity_history)} D/E years, current D/E: {debt_to_equity}")

        fundamentals = {
            'ticker': ticker,
            'cik': cik,
            'company_name': company_facts.get('entityName', ''),
            'eps_history': eps_history,
            'revenue_history': revenue_history,
            'debt_to_equity': debt_to_equity,
            'debt_to_equity_history': debt_to_equity_history
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

            logger.info(f"[{ticker}] Found {len(filings)} 10-K/10-Q filings")
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
        logger.info(f"[{ticker}] Extracting sections from {filing_type} using edgartools")
        sections = {}

        try:
            # Get company and latest filing
            company = Company(ticker)
            filings = company.get_filings(form=filing_type)

            if not filings:
                logger.warning(f"[{ticker}] No {filing_type} filings found")
                return {}

            latest_filing = filings.latest()
            filing_date = str(latest_filing.filing_date)
            logger.info(f"[{ticker}] Found {filing_type} filing from {filing_date}")

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
                    logger.info(f"[{ticker}] Extracted Item 1 (Business): {len(filing_obj.business)} chars")

                if hasattr(filing_obj, 'risk_factors') and filing_obj.risk_factors:
                    sections['risk_factors'] = {
                        'content': filing_obj.risk_factors,
                        'filing_type': '10-K',
                        'filing_date': filing_date
                    }
                    logger.info(f"[{ticker}] Extracted Item 1A (Risk Factors): {len(filing_obj.risk_factors)} chars")

                if hasattr(filing_obj, 'management_discussion') and filing_obj.management_discussion:
                    sections['mda'] = {
                        'content': filing_obj.management_discussion,
                        'filing_type': '10-K',
                        'filing_date': filing_date
                    }
                    logger.info(f"[{ticker}] Extracted Item 7 (MD&A): {len(filing_obj.management_discussion)} chars")

                # Try to get Item 7A (Market Risk) via bracket notation
                try:
                    market_risk = filing_obj["Item 7A"]
                    if market_risk:
                        sections['market_risk'] = {
                            'content': market_risk,
                            'filing_type': '10-K',
                            'filing_date': filing_date
                        }
                        logger.info(f"[{ticker}] Extracted Item 7A (Market Risk): {len(market_risk)} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[{ticker}] Item 7A (Market Risk) not available")

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
                        logger.info(f"[{ticker}] Extracted Item 2 (MD&A): {len(str(mda))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[{ticker}] Item 2 (MD&A) not available in 10-Q")

                try:
                    market_risk = filing_obj["Item 3"]
                    if market_risk:
                        sections['market_risk'] = {
                            'content': market_risk,
                            'filing_type': '10-Q',
                            'filing_date': filing_date
                        }
                        logger.info(f"[{ticker}] Extracted Item 3 (Market Risk): {len(str(market_risk))} chars")
                except (KeyError, AttributeError):
                    logger.info(f"[{ticker}] Item 3 (Market Risk) not available in 10-Q")

            logger.info(f"[{ticker}] Successfully extracted {len(sections)} sections from {filing_type}")
            return sections

        except Exception as e:
            logger.error(f"[{ticker}] Error extracting {filing_type} sections: {e}")
            import traceback
            traceback.print_exc()
            return {}
