# ABOUTME: Mixin for parsing net income data from SEC EDGAR company facts
# ABOUTME: Handles annual and quarterly net income extraction with Q4 calculation from annual totals

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class IncomeMixin:

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

