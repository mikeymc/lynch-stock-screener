# ABOUTME: Mixin for parsing cash flow data from SEC EDGAR company facts
# ABOUTME: Handles annual/quarterly OCF, CapEx, FCF, cash equivalents, and interest expense

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class CashFlowMixin:

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

    def parse_cash_equivalents_history(self, company_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract Cash and Cash Equivalents history from company facts.
        
        This function tries ALL available cash tags and merges the data to get the most
        complete coverage. This handles companies that change reporting tags over time.

        Args:
            company_facts: Company facts data from EDGAR API

        Returns:
            List of dictionaries with year, cash_and_cash_equivalents, and fiscal_end values
        """
        # All possible balance sheet cash tags (not cash flow tags)
        cash_tag_candidates = [
            'CashAndCashEquivalentsAtCarryingValue',
            'CashAndCashEquivalents',
            'CashCashEquivalentsAndShortTermInvestments',
            'Cash',
            'CashEquivalents',
            'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
            'CashAndDueFromBanks',  # Banks
            'CashFDICInsuredAmount',  # Banks
            'RestrictedCashAndCashEquivalents',
            'RestrictedCash',
        ]
        
        all_cash_data = {}  # {tag_name: {year: {data}}}
        
        # Try US-GAAP first
        try:
            if 'us-gaap' in company_facts['facts']:
                for tag in cash_tag_candidates:
                    if tag not in company_facts['facts']['us-gaap']:
                        continue
                    
                    units = company_facts['facts']['us-gaap'][tag].get('units', {})
                    if 'USD' not in units:
                        continue
                    
                    cash_data_list = units['USD']
                    by_year = {}
                    
                    for entry in cash_data_list:
                        if entry.get('form') in ['10-K', '20-F']:
                            fiscal_end = entry.get('end')
                            val = entry.get('val')
                            fy = entry.get('fy')  # Use EDGAR's fiscal year field
                            
                            if val is not None and fiscal_end and fy:
                                # Keep latest fiscal_end for each fiscal year (handles restatements)
                                if fy not in by_year or fiscal_end > by_year[fy]['fiscal_end']:
                                    by_year[fy] = {
                                        'year': fy,
                                        'fiscal_end': fiscal_end,
                                        'cash_and_cash_equivalents': val
                                    }
                    
                    if by_year:
                        all_cash_data[tag] = by_year
                        logger.debug(f"Tag {tag}: {len(by_year)} years of data")
        
        except (KeyError, TypeError):
            pass

        # Try IFRS if no US-GAAP data found
        if not all_cash_data:
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
                            else:
                                cash_data_list = None
                        
                        if cash_data_list:
                            by_year = {}
                            for entry in cash_data_list:
                                if entry.get('form') in ['10-K', '20-F']:
                                    fiscal_end = entry.get('end')
                                    val = entry.get('val')
                                    fy = entry.get('fy')
                                    
                                    if val is not None and fiscal_end and fy:
                                        if fy not in by_year or fiscal_end > by_year[fy]['fiscal_end']:
                                            by_year[fy] = {
                                                'year': fy,
                                                'fiscal_end': fiscal_end,
                                                'cash_and_cash_equivalents': val
                                            }
                            
                            if by_year:
                                all_cash_data['CashAndCashEquivalents (IFRS)'] = by_year
            except (KeyError, TypeError):
                pass

        if not all_cash_data:
            logger.debug("Could not parse Cash and Cash Equivalents history from EDGAR")
            return []

        # Merge all tags, preferring data from tags with more complete recent coverage
        # Strategy: Combine all years from all tags, preferring the latest fiscal_end for each year
        merged_by_year = {}
        
        for tag, by_year in all_cash_data.items():
            for year, data in by_year.items():
                if year not in merged_by_year:
                    merged_by_year[year] = data
                else:
                    # If we already have this year, keep the one with the later fiscal_end
                    if data['fiscal_end'] > merged_by_year[year]['fiscal_end']:
                        merged_by_year[year] = data
        
        annual_cash = list(merged_by_year.values())
        annual_cash.sort(key=lambda x: x['year'], reverse=True)

        # Log which tags contributed data
        if annual_cash and all_cash_data:
            tag_names = list(all_cash_data.keys())
            logger.info(f"Successfully parsed {len(annual_cash)} years of Cash from {len(tag_names)} tag(s): {', '.join(tag_names[:3])}")
        
        return annual_cash

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
