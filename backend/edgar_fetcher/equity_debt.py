# ABOUTME: Mixin for parsing shareholder equity, debt-to-equity, and tax rate data from EDGAR
# ABOUTME: Handles annual/quarterly equity, D/E ratio calculations, and effective tax rate extraction

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class EquityDebtMixin:

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

    def parse_debt_to_equity(self, company_facts: Dict[str, Any]) -> Optional[float]:
        """
        Calculate debt-to-equity ratio from company facts

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            Debt-to-equity ratio or None if data unavailable
        """
        try:
            facts = None
            if 'us-gaap' in company_facts.get('facts', {}):
                facts = company_facts['facts']['us-gaap']
            elif 'ifrs-full' in company_facts.get('facts', {}):
                facts = company_facts['facts']['ifrs-full']

            if facts is None:
                return None

            # Get most recent equity value
            equity_tags = ['StockholdersEquity', 'Equity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest']
            equity_data = []
            for tag in equity_tags:
                equity_data = facts.get(tag, {}).get('units', {}).get('USD', [])
                if equity_data:
                    break

            if not equity_data:
                return None

            # Find most recent 10-K or 20-F entry
            equity_entries = [e for e in equity_data if e.get('form') in ['10-K', '20-F']]
            if not equity_entries:
                return None

            equity_entries.sort(key=lambda x: x.get('end', ''), reverse=True)
            equity = equity_entries[0].get('val')
            fiscal_end = equity_entries[0].get('end', '')

            # LongTermDebtNoncurrent = long-term debt
            lt_tags = [
                'LongTermDebtNoncurrent',
                'LongTermDebt',
                'NonCurrentBorrowings', # IFRS
                'NonCurrentFinancialLiabilities', # IFRS
                'InterestBearingLoansAndBorrowingsNonCurrent' # IFRS
            ]
            long_term_debt = 0
            for tag in lt_tags:
                tag_data = facts.get(tag, {}).get('units', {}).get('USD', [])
                if tag_data:
                    matching_entries = [e for e in tag_data if e.get('form') in ['10-K', '20-F'] and e.get('end', '') == fiscal_end]
                    if matching_entries:
                        long_term_debt = matching_entries[0].get('val', 0)
                        break

            # LongTermDebtCurrent = current portion of long-term debt (short-term)
            st_tags = [
                'LongTermDebtCurrent',
                'DebtCurrent',
                'CurrentBorrowings', # IFRS
                'CurrentFinancialLiabilities', # IFRS
                'InterestBearingLoansAndBorrowingsCurrent' # IFRS
            ]
            short_term_debt = 0
            for tag in st_tags:
                tag_data = facts.get(tag, {}).get('units', {}).get('USD', [])
                if tag_data:
                    matching_entries = [e for e in tag_data if e.get('form') in ['10-K', '20-F'] and e.get('end', '') == fiscal_end]
                    if matching_entries:
                        short_term_debt = matching_entries[0].get('val', 0)
                        break

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
            facts = None
            if 'us-gaap' in company_facts.get('facts', {}):
                facts = company_facts['facts']['us-gaap']
            elif 'ifrs-full' in company_facts.get('facts', {}):
                facts = company_facts['facts']['ifrs-full']

            if facts is None:
                return []

            # Get equity data - try multiple tags in order of preference
            equity_tags = [
                'StockholdersEquity',
                'Equity', # IFRS
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
                'NonCurrentBorrowings', # IFRS
                'NonCurrentFinancialLiabilities', # IFRS
                'InterestBearingLoansAndBorrowingsNonCurrent', # IFRS
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
                'CurrentBorrowings', # IFRS
                'CurrentFinancialLiabilities', # IFRS
                'InterestBearingLoansAndBorrowingsCurrent', # IFRS
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

            # Filter for annual reports (10-K for US, 20-F for foreign) and create lookup by fiscal year and end date
            equity_by_year = {}
            for entry in equity_data:
                if entry.get('form') in ['10-K', '20-F']:
                    year = entry.get('fy')
                    fiscal_end = entry.get('end')
                    val = entry.get('val')
                    if year and val and year not in equity_by_year:
                        equity_by_year[year] = {'val': val, 'fiscal_end': fiscal_end}

            # Build long-term debt by year (first entry per year wins)
            long_term_debt_by_year = {}
            if long_term_debt_data:
                for entry in long_term_debt_data:
                    if entry.get('form') in ['10-K', '20-F']:
                        year = entry.get('fy')
                        fiscal_end = entry.get('end')
                        val = entry.get('val')
                        if year and val is not None and year not in long_term_debt_by_year:
                            long_term_debt_by_year[year] = {'val': val, 'fiscal_end': fiscal_end}

            # Build short-term debt by year
            short_term_debt_by_year = {}
            if short_term_debt_data:
                for entry in short_term_debt_data:
                    if entry.get('form') in ['10-K', '20-F']:
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
            facts = None
            if 'us-gaap' in company_facts.get('facts', {}):
                facts = company_facts['facts']['us-gaap']
            elif 'ifrs-full' in company_facts.get('facts', {}):
                facts = company_facts['facts']['ifrs-full']

            if facts is None:
                return []

            # Get equity data
            equity_tags = [
                'StockholdersEquity',
                'Equity', # IFRS
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
                'NonCurrentBorrowings', # IFRS
                'NonCurrentFinancialLiabilities', # IFRS
                'InterestBearingLoansAndBorrowingsNonCurrent', # IFRS
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
        tax_tags = ['IncomeTaxExpenseBenefit', 'IncomeTaxExpenseBenefitContinuingOperations', 'IncomeTaxExpenseContinunigOperations', 'IncomeTaxExpense']
        tax_data = []

        try:
            target_facts = None
            if 'us-gaap' in company_facts.get('facts', {}):
                target_facts = company_facts['facts']['us-gaap']
            elif 'ifrs-full' in company_facts.get('facts', {}):
                target_facts = company_facts['facts']['ifrs-full']

            if target_facts:
                for tag in tax_tags:
                    if tag in target_facts:
                        units = target_facts[tag]['units']
                        # Find USD or first currency
                        currency_unit = 'USD' if 'USD' in units else next(iter(u for u in units.keys() if len(u) == 3 and u.isupper()), None)
                        if currency_unit:
                            tax_data.extend(units[currency_unit])
        except (KeyError, TypeError):
            pass

        # Fetch Pretax Income
        pretax_tags = [
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxes',
            'ProfitLossBeforeTax' # IFRS
        ]
        pretax_data = []

        try:
            if target_facts:
                for tag in pretax_tags:
                    if tag in target_facts:
                        units = target_facts[tag]['units']
                        currency_unit = 'USD' if 'USD' in units else next(iter(u for u in units.keys() if len(u) == 3 and u.isupper()), None)
                        if currency_unit:
                            pretax_data.extend(units[currency_unit])
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
