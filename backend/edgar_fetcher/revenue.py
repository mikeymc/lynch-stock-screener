# ABOUTME: Mixin for parsing revenue data from SEC EDGAR company facts
# ABOUTME: Handles annual and quarterly revenue extraction with cumulative-to-individual conversion

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class RevenueMixin:

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

                            if revenue is not None and fiscal_end:
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

                                    if revenue is not None and fiscal_end:
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
