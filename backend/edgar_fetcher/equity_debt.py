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
        # Try all US-GAAP equity tags. Listed from most standard to most specific so that
        # standard tags win when there are conflicts within the same fiscal year.
        equity_tag_candidates = [
            'StockholdersEquity',
            'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
            'PartnersCapital',          # Partnerships / MLPs
            'CommonStockholdersEquity', # Some utilities and industrials
            'MembersEquity',            # LLC-structured companies
            'CommonEquityTierOneCapital', # Banks / financial institutions
        ]

        all_equity_data = {}  # {tag: {year: {val, fiscal_end}}}
        facts = company_facts.get('facts', {})

        for tag in equity_tag_candidates:
            units = facts.get('us-gaap', {}).get(tag, {}).get('units', {})
            if 'USD' not in units:
                continue

            by_year = {}
            for entry in units['USD']:
                if entry.get('form') in ['10-K', '20-F']:
                    fiscal_end = entry.get('end')
                    val = entry.get('val')
                    if val is not None and fiscal_end:
                        year = int(fiscal_end[:4])
                        if year not in by_year or fiscal_end > by_year[year]['fiscal_end']:
                            by_year[year] = {'val': val, 'fiscal_end': fiscal_end}
            if by_year:
                all_equity_data[tag] = by_year
                logger.debug(f"Found equity data via tag: {tag}")

        # Try IFRS if no US-GAAP data found
        if not all_equity_data:
            try:
                ifrs_units = facts.get('ifrs-full', {}).get('Equity', {}).get('units', {})
                currency = 'USD' if 'USD' in ifrs_units else next(
                    (u for u in ifrs_units if len(u) == 3 and u.isupper()), None
                )
                if currency:
                    by_year = {}
                    for entry in ifrs_units[currency]:
                        if entry.get('form') in ['20-F']:
                            fiscal_end = entry.get('end')
                            val = entry.get('val')
                            if val is not None and fiscal_end:
                                year = int(fiscal_end[:4])
                                if year not in by_year or fiscal_end > by_year[year]['fiscal_end']:
                                    by_year[year] = {'val': val, 'fiscal_end': fiscal_end}
                    if by_year:
                        all_equity_data['ifrs:Equity'] = by_year
                        logger.debug(f"Found equity data via IFRS Equity ({currency})")
            except (KeyError, TypeError):
                pass

        if not all_equity_data:
            logger.debug("Could not parse Shareholder Equity history from EDGAR")
            return []

        # Merge tags: iterate in reverse order so standard tags (listed first) overwrite
        # less standard ones when both cover the same year.
        merged_by_year = {}
        for tag in reversed(list(all_equity_data.keys())):
            for year, data in all_equity_data[tag].items():
                if year not in merged_by_year or data['fiscal_end'] >= merged_by_year[year]['fiscal_end']:
                    merged_by_year[year] = data

        annual_equity = [
            {'year': year, 'shareholder_equity': data['val'], 'fiscal_end': data['fiscal_end']}
            for year, data in merged_by_year.items()
        ]
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

            # Get equity data - collect from ALL tags to handle changes over time
            equity_tag_candidates = [
                'StockholdersEquity',
                'Equity', # IFRS
                'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
                'CommonStockholdersEquity',
                'MembersEquity', # LLCs
                'PartnersCapital', # Partnerships
                'CommonEquityTierOneCapital', # Banks
                'LiabilitiesAndStockholdersEquity'  # Last resort - total assets
            ]

            all_equity_data = {} # {tag: {year: {val, fiscal_end}}}
            for tag in equity_tag_candidates:
                units = facts.get(tag, {}).get('units', {})
                if 'USD' not in units:
                    continue
                
                data_list = units['USD']
                by_year = {}
                for entry in data_list:
                    if entry.get('form') in ['10-K', '20-F']:
                        year = entry.get('fy')
                        fiscal_end = entry.get('end')
                        val = entry.get('val')
                        if year and val is not None:
                            if year not in by_year or fiscal_end > by_year[year]['fiscal_end']:
                                by_year[year] = {'val': val, 'fiscal_end': fiscal_end}
                if by_year:
                    all_equity_data[tag] = by_year

            # Merge equity tags, preferring more modern/standard ones but keeping latest fiscal_end per year
            merged_equity_by_year = {}
            for tag in reversed(equity_tag_candidates): # Reverse so standard tags can overwrite if same year/end
                if tag in all_equity_data:
                    for year, data in all_equity_data[tag].items():
                        if year not in merged_equity_by_year or data['fiscal_end'] >= merged_equity_by_year[year]['fiscal_end']:
                            merged_equity_by_year[year] = data

            if not merged_equity_by_year:
                logger.debug("No equity data found in EDGAR")
                return []

            # Get debt data - collect from ALL tags to handle changes over time
            lt_debt_tag_candidates = [
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

            st_debt_tag_candidates = [
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
                'OtherLongTermDebtCurrent',
                'DebtSecuritiesCurrent'
            ]

            # Collect all debt data
            all_lt_debt = {}
            all_st_debt = {}

            def collect_debt_by_year(tags, facts_dict, target_dict):
                for tag in tags:
                    units = facts_dict.get(tag, {}).get('units', {})
                    if 'USD' not in units:
                        continue
                    
                    data_list = units['USD']
                    for entry in data_list:
                        if entry.get('form') in ['10-K', '20-F']:
                            year = entry.get('fy')
                            fiscal_end = entry.get('end')
                            val = entry.get('val')
                            if year and val is not None:
                                if tag not in target_dict:
                                    target_dict[tag] = {}
                                if year not in target_dict[tag] or fiscal_end > target_dict[tag][year]['fiscal_end']:
                                    target_dict[tag][year] = {'val': val, 'fiscal_end': fiscal_end}

            collect_debt_by_year(lt_debt_tag_candidates, facts, all_lt_debt)
            collect_debt_by_year(st_debt_tag_candidates, facts, all_st_debt)

            # Merge debt tags by year
            merged_lt_debt = {}
            for year_data in all_lt_debt.values():
                for year, data in year_data.items():
                    if year not in merged_lt_debt or data['fiscal_end'] > merged_lt_debt[year]['fiscal_end']:
                        merged_lt_debt[year] = data

            merged_st_debt = {}
            for year_data in all_st_debt.values():
                for year, data in year_data.items():
                    if year not in merged_st_debt or data['fiscal_end'] > merged_st_debt[year]['fiscal_end']:
                        merged_st_debt[year] = data

            # Calculate D/E ratio for each year where we have equity
            debt_to_equity_history = []
            for year, data in merged_equity_by_year.items():
                equity = data['val']
                fiscal_end = data['fiscal_end']

                total_debt = 0
                if year in merged_lt_debt:
                    total_debt += merged_lt_debt[year]['val']
                if year in merged_st_debt:
                    total_debt += merged_st_debt[year]['val']

                if equity != 0:
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

            # Get equity data - collect from ALL tags to handle changes over time
            equity_tag_candidates = [
                'StockholdersEquity',
                'Equity', # IFRS
                'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
                'CommonStockholdersEquity',
                'MembersEquity', # LLCs
                'PartnersCapital', # Partnerships
                'CommonEquityTierOneCapital', # Banks
                'LiabilitiesAndStockholdersEquity'  # Last resort - total assets
            ]

            all_equity_data = {} # {tag: {(year, quarter): {val, fiscal_end}}}
            
            def organize_by_quarter(data_list):
                by_quarter = {}
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
                    
                    if val is not None:
                        if key not in by_quarter or fiscal_end > by_quarter[key]['fiscal_end']:
                            by_quarter[key] = {'val': val, 'fiscal_end': fiscal_end}
                return by_quarter

            for tag in equity_tag_candidates:
                units = facts.get(tag, {}).get('units', {})
                if 'USD' not in units:
                    continue
                
                res = organize_by_quarter(units['USD'])
                if res:
                    all_equity_data[tag] = res

            # Merge equity tags, preferring more standard ones but keeping latest fiscal_end per quarter
            merged_equity_by_quarter = {}
            for tag in reversed(equity_tag_candidates):
                if tag in all_equity_data:
                    for key, data in all_equity_data[tag].items():
                        if key not in merged_equity_by_quarter or data['fiscal_end'] >= merged_equity_by_quarter[key]['fiscal_end']:
                            merged_equity_by_quarter[key] = data

            if not merged_equity_by_quarter:
                logger.debug("No quarterly equity data found in EDGAR")
                return []

            # Get debt data - collect from ALL tags
            lt_debt_tag_candidates = [
                'LongTermDebtNoncurrent',
                'LongTermDebt',
                'NonCurrentBorrowings',
                'NonCurrentFinancialLiabilities',
                'InterestBearingLoansAndBorrowingsNonCurrent',
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

            st_debt_tag_candidates = [
                'LongTermDebtCurrent',
                'DebtCurrent',
                'CurrentBorrowings',
                'CurrentFinancialLiabilities',
                'InterestBearingLoansAndBorrowingsCurrent',
                'NotesPayableCurrent',
                'ConvertibleNotesPayableCurrent',
                'ShortTermBorrowings',
                'CommercialPaper',
                'LinesOfCreditCurrent',
                'CapitalLeaseObligationsCurrent',
                'OtherLongTermDebtCurrent',
                'DebtSecuritiesCurrent'
            ]

            all_lt_debt = {} # {tag: {(year, quarter): {val, fiscal_end}}}
            all_st_debt = {}

            for tag in lt_debt_tag_candidates:
                units = facts.get(tag, {}).get('units', {})
                if 'USD' in units:
                    res = organize_by_quarter(units['USD'])
                    if res: all_lt_debt[tag] = res

            for tag in st_debt_tag_candidates:
                units = facts.get(tag, {}).get('units', {})
                if 'USD' in units:
                    res = organize_by_quarter(units['USD'])
                    if res: all_st_debt[tag] = res

            # Merge debt tags by (year, quarter)
            merged_lt_debt = {}
            for q_data in all_lt_debt.values():
                for key, data in q_data.items():
                    if key not in merged_lt_debt or data['fiscal_end'] > merged_lt_debt[key]['fiscal_end']:
                        merged_lt_debt[key] = data

            # Merge short-term debt tags
            merged_st_debt = {}
            for q_data in all_st_debt.values():
                for key, data in q_data.items():
                    if key not in merged_st_debt or data['fiscal_end'] > merged_st_debt[key]['fiscal_end']:
                        merged_st_debt[key] = data

            quarterly_de = []

            # Calculate D/E ratio for each quarter where we have equity
            for key, data in merged_equity_by_quarter.items():
                year, quarter = key
                equity = data['val']
                fiscal_end = data['fiscal_end']

                total_debt = 0
                if key in merged_lt_debt:
                    total_debt += merged_lt_debt[key]['val']
                if key in merged_st_debt:
                    total_debt += merged_st_debt[key]['val']

                if equity != 0:
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
