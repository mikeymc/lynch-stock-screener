# ABOUTME: Mixin for parsing shares outstanding data from SEC EDGAR company facts
# ABOUTME: Handles annual/quarterly share counts with normalization and split detection

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class SharesMixin:

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
