# ABOUTME: Mixin for fetching and storing earnings data from EDGAR and yfinance
# ABOUTME: Handles annual/quarterly earnings history, including gap-filling from yfinance

import logging
from typing import Dict, Any, Optional, List
import pandas as pd

logger = logging.getLogger(__name__)


class EarningsMixin:
    # todo: do we need calcualted_eps_history? can we ditch eps altogether?
    # todo: rename to _store_edgar_annual_earnings
    def _store_edgar_earnings(self, symbol: str, edgar_data: Dict[str, Any], price_history: Optional[pd.DataFrame] = None):
        """Store earnings history from EDGAR data using Net Income"""
        # Use net_income_annual (raw Net Income from EDGAR)
        net_income_annual = edgar_data.get('net_income_annual', [])
        revenue_history = edgar_data.get('revenue_history', [])
        debt_to_equity_history = edgar_data.get('debt_to_equity_history', [])
        shareholder_equity_history = edgar_data.get('shareholder_equity_history', [])
        calculated_eps_history = edgar_data.get('calculated_eps_history', [])
        cash_flow_history = edgar_data.get('cash_flow_history', [])

        # Parse dividend history
        dividend_history = edgar_data.get('dividend_history', [])
        # Filter for annual dividends or aggregate quarterly if needed
        # For now, let's assume we can match by year.
        # Note: EDGAR dividends might be quarterly. We should sum them up for annual.

        # Group dividends by year and period
        divs_grouped = {}
        for div in dividend_history:
            year = div['year']
            if year not in divs_grouped:
                divs_grouped[year] = {'annual': [], 'quarterly': []}

            if div.get('period') == 'annual':
                divs_grouped[year]['annual'].append(div['amount'])
            else:
                divs_grouped[year]['quarterly'].append(div['amount'])

        dividends_by_year = {}
        for year, groups in divs_grouped.items():
            if groups['annual']:
                # Use the max annual value (in case of duplicates/restatements)
                dividends_by_year[year] = max(groups['annual'])
            elif groups['quarterly']:
                # Sum quarterly values
                dividends_by_year[year] = sum(groups['quarterly'])

        # Create mapping of year to net income for easy lookup
        net_income_by_year = {entry['year']: {'net_income': entry['net_income'], 'fiscal_end': entry.get('fiscal_end')} for entry in net_income_annual}

        # Create mapping of year to debt_to_equity for easy lookup
        debt_to_equity_by_year = {entry['year']: entry['debt_to_equity'] for entry in debt_to_equity_history}

        # Create mapping of year to shareholder_equity for easy lookup
        shareholder_equity_by_year = {entry['year']: entry['shareholder_equity'] for entry in shareholder_equity_history}

        # Create mapping of year to shares_outstanding for easy lookup
        shares_outstanding_history = edgar_data.get('shares_outstanding_history', [])
        shares_outstanding_by_year = {entry['year']: entry['shares'] for entry in shares_outstanding_history}

        # Create mapping of year to cash_and_cash_equivalents for easy lookup
        cash_equivalents_history = edgar_data.get('cash_equivalents_history', [])
        cash_equivalents_by_year = {entry['year']: entry['cash_and_cash_equivalents'] for entry in cash_equivalents_history}

        # Create mapping of year to EPS - prioritize calculated EPS, fallback to direct EPS
        # calculated_eps_history = Net Income / Shares Outstanding (split-adjusted)
        # eps_history = Direct EPS from SEC filings (may not be split-adjusted for older years)
        calculated_eps_by_year = {entry['year']: entry['eps'] for entry in (calculated_eps_history or [])}
        direct_eps_by_year = {entry['year']: entry['eps'] for entry in edgar_data.get('eps_history', [])}

        # Detect stock splits by looking for sudden large drops in direct EPS between adjacent years
        # This indicates a stock split occurred (e.g., 20:1 split would show EPS dropping by ~95%)
        split_year = None
        split_adjustment_factor = 1.0
        best_split_ratio = 0

        if len(direct_eps_by_year) >= 2:
            sorted_years = sorted(direct_eps_by_year.keys())
            common_splits = [2, 3, 4, 5, 10, 20, 50, 100]

            for i in range(len(sorted_years) - 1):
                year1, year2 = sorted_years[i], sorted_years[i + 1]
                eps1, eps2 = direct_eps_by_year[year1], direct_eps_by_year[year2]

                if eps1 and eps2 and eps1 > 0 and eps2 > 0:
                    # Check for sudden drop (split would cause EPS to drop significantly)
                    ratio = eps1 / eps2
                    # Use 30% tolerance to account for earnings changes in the same year as split
                    for split in common_splits:
                        if 0.7 * split <= ratio <= 1.3 * split:
                            # Only use this split if it's larger than previous matches
                            # This ensures we catch the biggest split (e.g., 20:1 not 2:1)
                            if split > best_split_ratio:
                                split_year = year2
                                split_adjustment_factor = split
                                best_split_ratio = split
                            break

        if split_year:
            logger.info(f"[{symbol}] Detected {int(split_adjustment_factor)}:1 stock split in {split_year} - will adjust pre-split EPS")

        # Merge: use calculated EPS if available, otherwise fall back to split-adjusted direct EPS
        eps_by_year = {}
        all_years = set(calculated_eps_by_year.keys()) | set(direct_eps_by_year.keys())
        for year in all_years:
            if year in calculated_eps_by_year:
                eps_by_year[year] = calculated_eps_by_year[year]
            elif year in direct_eps_by_year:
                # Apply split adjustment to direct EPS for years before the split
                raw_eps = direct_eps_by_year[year]
                if split_year and year < split_year:
                    adjusted_eps = raw_eps / split_adjustment_factor
                    eps_by_year[year] = adjusted_eps
                    logger.debug(f"[{symbol}] Split-adjusted EPS for {year}: ${raw_eps:.2f} -> ${adjusted_eps:.2f}")
                else:
                    eps_by_year[year] = raw_eps

        # Create mapping of year to Cash Flow for easy lookup
        cash_flow_by_year = {entry['year']: entry for entry in cash_flow_history}

        # Track years that need D/E data
        years_needing_de = []
        years_needing_cf = []

        # Store all revenue years (with or without net income)
        for rev_entry in revenue_history:
            year = rev_entry['year']
            revenue = rev_entry['revenue']
            fiscal_end = rev_entry.get('fiscal_end')
            debt_to_equity = debt_to_equity_by_year.get(year)
            shareholder_equity = shareholder_equity_by_year.get(year)
            shares_outstanding = shares_outstanding_by_year.get(year)
            cash_and_cash_equivalents = cash_equivalents_by_year.get(year)
            eps = eps_by_year.get(year)
            dividend = dividends_by_year.get(year)

            # Get net income if available for this year
            ni_data = net_income_by_year.get(year)
            net_income = ni_data['net_income'] if ni_data else None
            # Prefer revenue's fiscal_end, fall back to NI's fiscal_end if available
            if not fiscal_end and ni_data:
                fiscal_end = ni_data.get('fiscal_end')

            # Get cash flow data
            cf_data = cash_flow_by_year.get(year, {})
            operating_cash_flow = cf_data.get('operating_cash_flow')
            capital_expenditures = cf_data.get('capital_expenditures')
            free_cash_flow = cf_data.get('free_cash_flow')

            # Determine missing CF data
            missing_cf = (operating_cash_flow is None or free_cash_flow is None)
            if missing_cf:
                 years_needing_cf.append(year)

            # Debug: Log cash and shares data
            if cash_and_cash_equivalents is not None or shares_outstanding is not None:
                logger.info(f"[{symbol}] {year}: Storing cash=${cash_and_cash_equivalents}, shares={shares_outstanding}")

            self.db.save_earnings_history(symbol, year, float(eps) if eps else None, float(revenue), fiscal_end=fiscal_end, debt_to_equity=debt_to_equity, net_income=float(net_income) if net_income else None, dividend_amount=float(dividend) if dividend is not None else None, operating_cash_flow=float(operating_cash_flow) if operating_cash_flow is not None else None, capital_expenditures=float(capital_expenditures) if capital_expenditures is not None else None, free_cash_flow=float(free_cash_flow) if free_cash_flow is not None else None, shareholder_equity=float(shareholder_equity) if shareholder_equity is not None else None, shares_outstanding=float(shares_outstanding) if shares_outstanding is not None else None, cash_and_cash_equivalents=float(cash_and_cash_equivalents) if cash_and_cash_equivalents is not None else None)
            logger.debug(f"[{symbol}] Stored EDGAR for {year}: Revenue: ${revenue:,.0f}" + (f", NI: ${net_income:,.0f}" if net_income else " (no NI)") + (f", Div: ${dividend:.2f}" if dividend else "") + (f", FCF: ${free_cash_flow:,.0f}" if free_cash_flow else ""))

            # Track years missing D/E data
            if debt_to_equity is None:
                years_needing_de.append(year)

        # If EDGAR didn't provide D/E data, try to get it from yfinance
        if years_needing_de:
            logger.info(f"[{symbol}] EDGAR missing D/E for {len(years_needing_de)} years. Fetching from yfinance balance sheet")
            self._backfill_debt_to_equity(symbol, years_needing_de)

        if years_needing_cf:
            logger.info(f"[{symbol}] EDGAR missing Cash Flow for {len(years_needing_cf)} years. Fetching from yfinance cashflow")
            self._backfill_cash_flow(symbol, years_needing_cf)

    def _store_edgar_quarterly_earnings(self, symbol: str, edgar_data: Dict[str, Any], price_history: Optional[pd.DataFrame] = None, force_refresh: bool = False):
        """Store quarterly earnings history from EDGAR data (Net Income, Revenue, EPS, Cash Flow, D/E)"""
        # Get all quarterly data sources from EDGAR
        net_income_quarterly = edgar_data.get('net_income_quarterly', [])
        revenue_quarterly = edgar_data.get('revenue_quarterly', [])
        eps_quarterly = edgar_data.get('eps_quarterly', [])
        cash_flow_quarterly = edgar_data.get('cash_flow_quarterly', [])
        debt_to_equity_quarterly = edgar_data.get('debt_to_equity_quarterly', [])

        # Parse dividend history
        dividend_history = edgar_data.get('dividend_history', [])

        # Map dividends to (year, quarter)
        dividends_by_quarter = {}
        for div in dividend_history:
            if div.get('period') == 'quarterly' and div.get('quarter'):
                key = (div['year'], div['quarter'])
                dividends_by_quarter[key] = div['amount']

        if not any([net_income_quarterly, revenue_quarterly, cash_flow_quarterly, eps_quarterly, debt_to_equity_quarterly]):
            logger.warning(f"[{symbol}] No quarterly data available from EDGAR")
            return

        # Only clear existing quarterly data on force refresh
        if force_refresh:
            self.db.clear_quarterly_earnings(symbol)

        # Create lookup dictionaries keyed by (year, quarter)
        ni_by_key = {(e['year'], e['quarter']): e for e in net_income_quarterly}
        rev_by_key = {(e['year'], e['quarter']): e for e in revenue_quarterly}

        # Merge EPS sources: Prefer Reported, Fallback to Calculated
        eps_by_key = {}
        # First populate with calculated
        calculated_eps_quarterly = edgar_data.get('calculated_eps_quarterly', [])
        for e in calculated_eps_quarterly:
            eps_by_key[(e['year'], e['quarter'])] = e

        # Then overwrite with reported (if exists)
        eps_quarterly = edgar_data.get('eps_quarterly', [])
        for e in eps_quarterly:
             eps_by_key[(e['year'], e['quarter'])] = e

        cf_by_key = {(e['year'], e['quarter']): e for e in cash_flow_quarterly}
        de_by_key = {(e['year'], e['quarter']): e for e in debt_to_equity_quarterly}

        # Add shares_outstanding quarterly lookup
        shares_outstanding_quarterly = edgar_data.get('shares_outstanding_quarterly', [])
        so_by_key = {(e['year'], e['quarter']): e for e in shares_outstanding_quarterly}

        # Add shareholder_equity quarterly lookup
        shareholder_equity_quarterly = edgar_data.get('shareholder_equity_quarterly', [])
        equity_by_key = {(e['year'], e['quarter']): e for e in shareholder_equity_quarterly}

        # Merge all quarter keys
        all_keys = set(ni_by_key.keys()) | set(rev_by_key.keys()) | set(eps_by_key.keys()) | set(cf_by_key.keys()) | set(de_by_key.keys()) | set(so_by_key.keys()) | set(equity_by_key.keys())

        quarters_stored = 0
        for key in all_keys:
            year, quarter = key

            # Get data from each source
            ni_entry = ni_by_key.get(key, {})
            rev_entry = rev_by_key.get(key, {})
            eps_entry = eps_by_key.get(key, {})
            cf_entry = cf_by_key.get(key, {})
            de_entry = de_by_key.get(key, {})
            so_entry = so_by_key.get(key, {})
            equity_entry = equity_by_key.get(key, {})

            net_income = ni_entry.get('net_income')
            revenue = rev_entry.get('revenue')
            eps = eps_entry.get('eps')
            operating_cash_flow = cf_entry.get('operating_cash_flow')
            capital_expenditures = cf_entry.get('capital_expenditures')
            free_cash_flow = cf_entry.get('free_cash_flow')
            debt_to_equity = de_entry.get('debt_to_equity')
            shares_outstanding = so_entry.get('shares')
            shareholder_equity = equity_entry.get('shareholder_equity')

            # Use fiscal_end from whichever source has it
            fiscal_end = ni_entry.get('fiscal_end') or rev_entry.get('fiscal_end') or eps_entry.get('fiscal_end') or cf_entry.get('fiscal_end') or de_entry.get('fiscal_end') or equity_entry.get('fiscal_end')
            dividend = dividends_by_quarter.get(key)

            # Only store if we have at least some data (check D/E and Equity too)
            if net_income or revenue or eps or operating_cash_flow or free_cash_flow or debt_to_equity is not None or shareholder_equity is not None:
                self.db.save_earnings_history(
                    symbol,
                    year,
                    float(eps) if eps else None,
                    float(revenue) if revenue else None,
                    fiscal_end=fiscal_end,
                    debt_to_equity=float(debt_to_equity) if debt_to_equity is not None else None,
                    period=quarter,
                    net_income=float(net_income) if net_income else None,
                    dividend_amount=float(dividend) if dividend is not None else None,
                    operating_cash_flow=float(operating_cash_flow) if operating_cash_flow else None,
                    capital_expenditures=float(capital_expenditures) if capital_expenditures else None,
                    free_cash_flow=float(free_cash_flow) if free_cash_flow else None,
                    shares_outstanding=float(shares_outstanding) if shares_outstanding is not None else None,
                    shareholder_equity=float(shareholder_equity) if shareholder_equity is not None else None,
                    cash_and_cash_equivalents=None,  # Quarterly cash not currently tracked
                )
                quarters_stored += 1

        logger.info(f"[{symbol}] Stored {quarters_stored} quarters of EDGAR data (NI: {len(net_income_quarterly)}, Rev: {len(revenue_quarterly)}, EPS: {len(eps_quarterly)}, CF: {len(cash_flow_quarterly)})")



    def _fetch_and_store_earnings(self, symbol: str):
        try:
            # Fetch annual data with timeout protection
            financials = self._get_yf_financials(symbol)
            balance_sheet = self._get_yf_balance_sheet(symbol)
            cashflow = self._get_yf_cashflow(symbol)
            dividends = self._get_yf_dividends(symbol)
            price_history = self._get_yf_history(symbol)

            # Process dividends into annual sums
            dividends_by_year = {}
            if dividends is not None and not dividends.empty:
                # dividends is a Series with DateTime index
                for date, amount in dividends.items():
                    year = date.year
                    if year not in dividends_by_year:
                        dividends_by_year[year] = 0.0
                    dividends_by_year[year] += amount

            if financials is not None and not financials.empty:
                year_count = len(financials.columns)
                logger.info(f"[{symbol}] yfinance returned {year_count} years of annual data")

                if year_count < 5:
                    logger.warning(f"[{symbol}] Limited data: only {year_count} years available from yfinance")

                for col in financials.columns:
                    year = col.year if hasattr(col, 'year') else None
                    if not year:
                        continue

                    revenue = None
                    if 'Total Revenue' in financials.index:
                        revenue = financials.loc['Total Revenue', col]

                    eps = None
                    if 'Diluted EPS' in financials.index:
                        eps = financials.loc['Diluted EPS', col]

                    # Extract Net Income from yfinance financials
                    net_income = None
                    if 'Net Income' in financials.index:
                        net_income = financials.loc['Net Income', col]

                    # Calculate debt-to-equity from balance sheet
                    debt_to_equity = None
                    if balance_sheet is not None and not balance_sheet.empty and col in balance_sheet.columns:
                        debt_to_equity, _ = self._calculate_debt_to_equity(balance_sheet, col)

                    dividend = dividends_by_year.get(year)

                    if year and pd.notna(revenue) and pd.notna(eps):
                        # Extract cash flow metrics
                        operating_cash_flow = None
                        capital_expenditures = None
                        free_cash_flow = None

                        if cashflow is not None and not cashflow.empty and col in cashflow.columns:
                            if 'Operating Cash Flow' in cashflow.index:
                                operating_cash_flow = cashflow.loc['Operating Cash Flow', col]
                            elif 'Total Cash From Operating Activities' in cashflow.index:
                                operating_cash_flow = cashflow.loc['Total Cash From Operating Activities', col]

                            if 'Capital Expenditure' in cashflow.index:
                                capital_expenditures = cashflow.loc['Capital Expenditure', col]
                                # In yfinance, CapEx is usually negative. We want positive for storage (or consistent with EDGAR).
                                # EDGAR usually reports "Payments to Acquire..." which is positive number representing outflow.
                                # yfinance reports negative number. Let's flip it to positive to match "Payments..." concept?
                                # Actually, let's check EDGAR. EDGAR "NetCashProvidedByUsedIn..." is signed.
                                # "PaymentsToAcquire..." is usually positive in the tag, but contextually an outflow.
                                # Let's store signed values as they come from source, but be careful with FCF calc.
                                # yfinance: OCF is positive, CapEx is negative. FCF = OCF + CapEx.
                                # EDGAR: OCF is positive/negative. CapEx we extracted as "Payments...", usually positive.
                                # In parse_cash_flow_history we did FCF = OCF - CapEx.
                                # So for yfinance, if CapEx is negative, we should probably flip it to positive to match "Payments" concept
                                # OR just store it as is and handle it.
                                # Let's try to standardize: Store CapEx as a positive number representing the cost.
                                if capital_expenditures is not None and capital_expenditures < 0:
                                    capital_expenditures = -capital_expenditures

                            if 'Free Cash Flow' in cashflow.index:
                                free_cash_flow = cashflow.loc['Free Cash Flow', col]
                            elif operating_cash_flow is not None and capital_expenditures is not None:
                                free_cash_flow = operating_cash_flow - capital_expenditures

                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period='annual',
                                                     net_income=float(net_income) if pd.notna(net_income) else None,
                                                     dividend_amount=float(dividend) if dividend is not None else None,
                                                     operating_cash_flow=float(operating_cash_flow) if operating_cash_flow is not None else None,
                                                     capital_expenditures=float(capital_expenditures) if capital_expenditures is not None else None,
                                                     free_cash_flow=float(free_cash_flow) if free_cash_flow is not None else None)

            # Fetch quarterly data with timeout protection
            quarterly_financials = self._get_yf_quarterly_financials(symbol)
            quarterly_balance_sheet = self._get_yf_quarterly_balance_sheet(symbol)

            if quarterly_financials is not None and not quarterly_financials.empty:
                quarter_count = len(quarterly_financials.columns)
                logger.info(f"[{symbol}] yfinance returned {quarter_count} quarters of data")

                for col in quarterly_financials.columns:
                    year = col.year if hasattr(col, 'year') else None
                    quarter = col.quarter if hasattr(col, 'quarter') else None

                    if not year or not quarter:
                        continue

                    revenue = None
                    if 'Total Revenue' in quarterly_financials.index:
                        revenue = quarterly_financials.loc['Total Revenue', col]

                    eps = None
                    if 'Diluted EPS' in quarterly_financials.index:
                        eps = quarterly_financials.loc['Diluted EPS', col]

                    # Extract Net Income from quarterly financials
                    net_income = None
                    if 'Net Income' in quarterly_financials.index:
                        net_income = quarterly_financials.loc['Net Income', col]

                    # Calculate debt-to-equity from quarterly balance sheet
                    debt_to_equity = None
                    if quarterly_balance_sheet is not None and not quarterly_balance_sheet.empty and col in quarterly_balance_sheet.columns:
                        debt_to_equity, _ = self._calculate_debt_to_equity(quarterly_balance_sheet, col)

                    # Map dividends to (year, quarter)
                    # Note: We need to calculate dividends_by_quarter here or reuse from above if we move it up
                    # Since we didn't calculate it in this method yet, let's do it now
                    dividends_by_quarter = {}
                    if dividends is not None and not dividends.empty:
                        for date, amount in dividends.items():
                            year = date.year
                            month = date.month
                            quarter = (month - 1) // 3 + 1
                            key = (year, quarter)
                            if key not in dividends_by_quarter:
                                dividends_by_quarter[key] = 0.0
                            dividends_by_quarter[key] += amount

                    dividend = dividends_by_quarter.get((year, quarter))

                    if year and quarter and pd.notna(revenue) and pd.notna(eps):
                        period = f'Q{quarter}'
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period=period,
                                                     net_income=float(net_income) if pd.notna(net_income) else None,
                                                     dividend_amount=float(dividend) if dividend is not None else None)

        except Exception as e:
            logger.error(f"[{symbol}] Error fetching earnings from yfinance: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def _fetch_quarterly_earnings(self, symbol: str):
        """Fetch and store ONLY quarterly earnings data from yfinance"""
        try:
            # Fetch quarterly data only with timeout protection
            quarterly_financials = self._get_yf_quarterly_financials(symbol)
            quarterly_balance_sheet = self._get_yf_quarterly_balance_sheet(symbol)
            dividends = self._get_yf_dividends(symbol)
            price_history = self._get_yf_history(symbol)

            # Map dividends to (year, quarter)
            dividends_by_quarter = {}
            if dividends is not None and not dividends.empty:
                for date, amount in dividends.items():
                    year = date.year
                    month = date.month
                    # Estimate quarter based on month
                    quarter = (month - 1) // 3 + 1
                    key = (year, quarter)
                    if key not in dividends_by_quarter:
                        dividends_by_quarter[key] = 0.0
                    dividends_by_quarter[key] += amount

            if quarterly_financials is not None and not quarterly_financials.empty:
                quarter_count = len(quarterly_financials.columns)
                logger.info(f"[{symbol}] yfinance returned {quarter_count} quarters of data")

                for col in quarterly_financials.columns:
                    year = col.year if hasattr(col, 'year') else None
                    quarter = col.quarter if hasattr(col, 'quarter') else None

                    if not year or not quarter:
                        continue

                    revenue = None
                    if 'Total Revenue' in quarterly_financials.index:
                        revenue = quarterly_financials.loc['Total Revenue', col]

                    eps = None
                    if 'Diluted EPS' in quarterly_financials.index:
                        eps = quarterly_financials.loc['Diluted EPS', col]

                    # Extract Net Income from quarterly financials
                    net_income = None
                    if 'Net Income' in quarterly_financials.index:
                        net_income = quarterly_financials.loc['Net Income', col]

                    # Calculate debt-to-equity from quarterly balance sheet
                    debt_to_equity = None
                    if quarterly_balance_sheet is not None and not quarterly_balance_sheet.empty and col in quarterly_balance_sheet.columns:
                        debt_to_equity, _ = self._calculate_debt_to_equity(quarterly_balance_sheet, col)

                    dividend = dividends_by_quarter.get((year, quarter))

                    if year and quarter and pd.notna(revenue) and pd.notna(eps):
                        period = f'Q{quarter}'
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period=period,
                                                     net_income=float(net_income) if pd.notna(net_income) else None,
                                                     dividend_amount=float(dividend) if dividend is not None else None)
            else:
                logger.warning(f"[{symbol}] No quarterly financial data available from yfinance")

        except Exception as e:
            logger.error(f"[{symbol}] Error fetching quarterly earnings from yfinance: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
