# ABOUTME: Mixin for fetching and parsing SEC filings (10-K, 10-Q, Form 4) from EDGAR
# ABOUTME: Handles filing section extraction, dividend history, and insider transaction parsing

import requests
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class FilingsMixin:

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
