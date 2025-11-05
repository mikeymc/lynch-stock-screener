# ABOUTME: Fetches financial data from SEC EDGAR API using CIK lookups
# ABOUTME: Provides historical EPS, revenue, and debt metrics from 10-K filings

import requests
import time
from typing import Dict, List, Optional, Any


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
            print(f"Error loading ticker-to-CIK mapping from EDGAR: {e}")
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
        return mapping.get(ticker.upper())

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
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching company facts for CIK {cik}: {e}")
            return None

    def parse_eps_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract EPS history from company facts

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year and eps values
        """
        try:
            eps_data = company_facts['facts']['us-gaap']['EarningsPerShareDiluted']['units']['USD/shares']

            # Filter for 10-K annual reports only
            annual_eps = []
            seen_years = set()

            for entry in eps_data:
                if entry.get('form') == '10-K':
                    year = entry.get('fy')
                    eps = entry.get('val')

                    # Avoid duplicates, keep only one entry per fiscal year
                    if year and eps and year not in seen_years:
                        annual_eps.append({
                            'year': year,
                            'eps': eps
                        })
                        seen_years.add(year)

            # Sort by year descending
            annual_eps.sort(key=lambda x: x['year'], reverse=True)
            return annual_eps

        except (KeyError, TypeError):
            return []

    def parse_revenue_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract revenue history from company facts

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year and revenue values
        """
        try:
            # Try multiple possible field names for revenue
            revenue_fields = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet']

            revenue_data = None
            for field in revenue_fields:
                try:
                    revenue_data = company_facts['facts']['us-gaap'][field]['units']['USD']
                    break
                except KeyError:
                    continue

            if not revenue_data:
                return []

            # Filter for 10-K annual reports only
            annual_revenue = []
            seen_years = set()

            for entry in revenue_data:
                if entry.get('form') == '10-K':
                    year = entry.get('fy')
                    revenue = entry.get('val')

                    # Avoid duplicates
                    if year and revenue and year not in seen_years:
                        annual_revenue.append({
                            'year': year,
                            'revenue': revenue
                        })
                        seen_years.add(year)

            # Sort by year descending
            annual_revenue.sort(key=lambda x: x['year'], reverse=True)
            return annual_revenue

        except (KeyError, TypeError):
            return []

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
            print(f"Could not find CIK for ticker {ticker}")
            return None

        # Fetch company facts
        company_facts = self.fetch_company_facts(cik)
        if not company_facts:
            return None

        # Parse all fundamental data
        fundamentals = {
            'ticker': ticker,
            'cik': cik,
            'company_name': company_facts.get('entityName', ''),
            'eps_history': self.parse_eps_history(company_facts),
            'revenue_history': self.parse_revenue_history(company_facts),
            'debt_to_equity': self.parse_debt_to_equity(company_facts)
        }

        return fundamentals
