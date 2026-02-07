# ABOUTME: Mixin for parsing EPS (Earnings Per Share) data from SEC EDGAR company facts
# ABOUTME: Handles annual/quarterly EPS, split-adjusted calculations, and cumulative-to-individual conversion

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class EPSMixin:

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
