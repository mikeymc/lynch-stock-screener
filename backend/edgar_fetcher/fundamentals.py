# ABOUTME: Mixin for fetching complete stock fundamentals from SEC EDGAR
# ABOUTME: Combines 10-Q filing parsing with company_facts for hybrid quarterly/annual data

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class FundamentalsMixin:

    def get_annual_map(self, data_list):
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

    def _extract_quarterly_from_raw_xbrl(self, ticker: str, income_statement, fiscal_year: int = None, fiscal_quarter: str = None) -> Dict[str, Any]:
        """
        Extract discrete quarterly values from income statement using get_raw_data().

        In edgartools 5.x, to_dataframe() no longer provides (Q) column suffixes.
        Instead, we use get_raw_data() which provides values with period keys like:
        - 'duration_2025-04-01_2025-06-30' for Q2 discrete (3 months)
        - 'duration_2025-01-01_2025-06-30' for 6-month YTD

        We identify quarterly values by finding periods with ~90 day duration.
        """
        result = {
            'revenue': None,
            'net_income': None,
            'eps': None,
            'fiscal_year': fiscal_year,
            'fiscal_quarter': fiscal_quarter,
            'fiscal_end': None
        }

        try:
            raw_data = income_statement.get_raw_data()
        except Exception as e:
            logger.warning(f"[{ticker}] Failed to get raw XBRL data: {e}")
            return result

        from datetime import datetime

        # First pass: find the quarter_period_key by scanning ALL items for a ~90-day duration.
        # This decouples period discovery from revenue extraction so that companies without
        # standard revenue labels (banks, pre-revenue biotechs, financials) still get their
        # NI and EPS extracted.
        quarter_period_key = None
        all_quarterly_periods = []

        for item in raw_data:
            if not item.get('has_values') or item.get('is_abstract') or item.get('is_dimension'):
                continue
            for period_key, val in item.get('values', {}).items():
                if not period_key.startswith('duration_'):
                    continue
                parts = period_key.replace('duration_', '').split('_')
                if len(parts) != 2:
                    continue
                try:
                    start = datetime.strptime(parts[0], '%Y-%m-%d')
                    end = datetime.strptime(parts[1], '%Y-%m-%d')
                    duration_days = (end - start).days
                    if 80 <= duration_days <= 100:
                        all_quarterly_periods.append({
                            'key': period_key,
                            'start': parts[0],
                            'end': parts[1],
                            'duration_days': duration_days
                        })
                except (ValueError, TypeError):
                    pass

        if all_quarterly_periods:
            # Sort by most recent end date, then shortest duration (most discrete)
            all_quarterly_periods.sort(key=lambda x: (-int(x['end'].replace('-', '')), x['duration_days']))
            best = all_quarterly_periods[0]
            quarter_period_key = best['key']
            result['fiscal_end'] = best['end']

        # Second pass: extract field values using the discovered period key
        for item in raw_data:
            if not item.get('has_values') or item.get('is_abstract') or item.get('is_dimension'):
                continue

            label = item.get('label', '')
            concept = item.get('concept', '')
            values = item.get('values', {})

            # Revenue: look for revenue/sales labels, exclude cost items
            is_revenue = ('revenue' in label.lower() or
                         'sales' in label.lower() or
                         concept.lower() == 'us-gaap_revenues')
            is_cost = 'cost' in label.lower()

            if is_revenue and not is_cost and not result['revenue'] and quarter_period_key:
                # Prefer the exact quarter_period_key; fall back to shortest matching period
                if quarter_period_key in values:
                    result['revenue'] = values[quarter_period_key]
                    logger.info(f"[{ticker}] Found discrete quarterly revenue: ${result['revenue']/1e9:.2f}B")
                else:
                    # Try other ~90-day periods in case revenue uses a slightly different date range
                    quarterly_periods = []
                    for period_key, val in values.items():
                        if not period_key.startswith('duration_'):
                            continue
                        parts = period_key.replace('duration_', '').split('_')
                        if len(parts) == 2:
                            try:
                                s = datetime.strptime(parts[0], '%Y-%m-%d')
                                e = datetime.strptime(parts[1], '%Y-%m-%d')
                                dur = (e - s).days
                                if 80 <= dur <= 100:
                                    quarterly_periods.append({'key': period_key, 'value': val, 'start': parts[0], 'end': parts[1], 'duration_days': dur})
                            except (ValueError, TypeError):
                                pass
                    if quarterly_periods:
                        quarterly_periods.sort(key=lambda x: (-int(x['end'].replace('-', '')), x['duration_days']))
                        best = quarterly_periods[0]
                        result['revenue'] = best['value']
                        logger.info(f"[{ticker}] Found discrete quarterly revenue (alt period): ${best['value']/1e9:.2f}B from {best['start']} to {best['end']}")

            # Net income
            is_net_income = ('net income' in label.lower() and
                           'per share' not in label.lower() and
                           'comprehensive' not in label.lower())

            if is_net_income and not result['net_income'] and quarter_period_key:
                if quarter_period_key in values:
                    result['net_income'] = values[quarter_period_key]
                    logger.info(f"[{ticker}] Found discrete quarterly Net Income: ${result['net_income']/1e9:.2f}B")

            # EPS (diluted)
            is_eps = ('diluted' in label.lower() and 'per share' in label.lower())

            if is_eps and not result['eps'] and quarter_period_key:
                if quarter_period_key in values:
                    result['eps'] = values[quarter_period_key]
                    logger.info(f"[{ticker}] Found discrete quarterly EPS: ${result['eps']:.2f}")

        # Infer fiscal quarter from fiscal_end date if not provided
        if result['fiscal_end'] and not result['fiscal_quarter']:
            try:
                m = int(result['fiscal_end'].split('-')[1])
                if m in [1, 2, 3]: result['fiscal_quarter'] = 'Q1'
                elif m in [4, 5, 6]: result['fiscal_quarter'] = 'Q2'
                elif m in [7, 8, 9]: result['fiscal_quarter'] = 'Q3'
                else: result['fiscal_quarter'] = 'Q4'
                result['fiscal_year'] = int(result['fiscal_end'].split('-')[0])
            except:
                pass

        return result



    def _first_date_column(self, df) -> Optional[str]:
        """
        Return the first column in df whose name matches YYYY-MM-DD.

        In edgartools 5.x, to_dataframe() produces bare date column headers
        instead of the old "YYYY-MM-DD (Qn)" format. The first date column is
        the most recent period snapshot.
        """
        import re
        _date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        for col in df.columns:
            if isinstance(col, str) and _date_re.match(col):
                return col
        return None

    def _extract_cf_from_raw_data(self, cf_raw: List[dict], period_key: str):
        """
        Extract OCF and capex from CF get_raw_data() for a specific period key.

        Returns (operating_cash_flow, capital_expenditures) where capex is
        stored as a positive value (abs of the raw outflow).
        """
        import math as _math
        operating_cash_flow = None
        capital_expenditures = None

        for item in cf_raw:
            if not item.get('has_values') or item.get('is_abstract') or item.get('is_dimension'):
                continue
            label = item.get('label', '')
            values = item.get('values', {})
            val = values.get(period_key)
            if val is None or (isinstance(val, float) and _math.isnan(val)):
                continue

            label_lower = label.lower()
            is_ocf = ('operating' in label_lower and 'cash' in label_lower)
            is_capex = (
                'capital expenditure' in label_lower or
                'capital addition' in label_lower or
                ('property' in label_lower and ('purchase' in label_lower or 'acquisition' in label_lower)) or
                ('purchases' in label_lower and 'equipment' in label_lower)
            )

            if is_ocf and operating_cash_flow is None:
                operating_cash_flow = val
            elif is_capex and capital_expenditures is None:
                capital_expenditures = abs(val)

        return operating_cash_flow, capital_expenditures

    def _compute_discrete_cf(self, cf_ytd_staging: List[dict]) -> List[dict]:
        """
        Convert YTD cumulative cash flow values to discrete quarterly values.

        Cash flow statements carry YTD values from fiscal year start.
        Q1 YTD equals Q1 discrete. Q2 discrete = Q2 YTD - Q1 YTD, etc.
        Year boundaries reset the accumulation so 2024 Q1 is never
        contaminated by 2023 Q4 YTD.
        """
        quarter_order = {'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}
        result = []

        by_year: Dict[int, List[dict]] = {}
        for entry in cf_ytd_staging:
            yr = entry.get('year')
            if yr is not None:
                by_year.setdefault(yr, []).append(entry)

        for yr, entries in sorted(by_year.items()):
            entries.sort(key=lambda x: quarter_order.get(x.get('quarter', 'Q1'), 0))
            prev_ocf = None
            prev_capex = None

            for i, entry in enumerate(entries):
                ocf_ytd = entry.get('ocf_ytd')
                capex_ytd = entry.get('capex_ytd')

                if i == 0:
                    ocf_discrete = ocf_ytd
                    capex_discrete = capex_ytd
                else:
                    ocf_discrete = (ocf_ytd - prev_ocf) if (ocf_ytd is not None and prev_ocf is not None) else ocf_ytd
                    capex_discrete = (capex_ytd - prev_capex) if (capex_ytd is not None and prev_capex is not None) else capex_ytd

                fcf = None
                if ocf_discrete is not None and capex_discrete is not None:
                    fcf = ocf_discrete - capex_discrete

                result.append({
                    'year': entry['year'],
                    'quarter': entry['quarter'],
                    'operating_cash_flow': ocf_discrete,
                    'capital_expenditures': capex_discrete,
                    'free_cash_flow': fcf,
                    'fiscal_end': entry['fiscal_end'],
                })

                if ocf_ytd is not None:
                    prev_ocf = ocf_ytd
                if capex_ytd is not None:
                    prev_capex = capex_ytd

        return result

    def get_quarterly_financials_from_filings(self, ticker: str, num_quarters: int = 8) -> Dict[str, Any]:
        """
        Extract quarterly financials directly from 10-Q and 10-K filings using edgartools.

        This method bypasses the outdated company_facts API and parses filings
        directly to extract all quarterly financial metrics. This solves issues with:
        - Missing data for companies like AAPL/MSFT (company_facts is outdated)
        - Incorrect data for companies like NFLX (prior-year comparatives)
        - Inconsistent XBRL tags across companies
        - Missing Q4 data (now extracted from 10-K)

        Args:
            ticker: Stock ticker symbol
            num_quarters: Number of recent filings to extract (default: 8)

        Returns:
            Dictionary containing quarterly data lists and metadata:
            - revenue_quarterly: List of {year, quarter, revenue, fiscal_end}
            - eps_quarterly: List of {year, quarter, eps, fiscal_end}
            - net_income_quarterly: List of {year, quarter, net_income, fiscal_end}
            - cash_flow_quarterly: List of {year, quarter, operating_cash_flow, capital_expenditures, free_cash_flow, fiscal_end}
            - debt_to_equity_quarterly: List of {year, quarter, debt_to_equity, fiscal_end}
            - shares_outstanding_quarterly: List of {year, quarter, shares, fiscal_end}
            - shareholder_equity_quarterly: List of {year, quarter, shareholder_equity, fiscal_end}
            - filings_metadata: List of {accession_number, form, date} for processed filings
        """
        try:
            # Get company object
            cik = self.get_cik_for_ticker(ticker)
            if not cik:
                logger.warning(f"[{ticker}] Could not find CIK")
                return {}

            company = self.get_company(cik)
            if not company:
                logger.warning(f"[{ticker}] Could not create Company object")
                return {}

            # Get recent 10-Q and 10-K filings
            filings = company.get_filings(form=["10-K", "10-Q"]).head(num_quarters)

            if not filings or len(filings) == 0:
                logger.warning(f"[{ticker}] No 10-K/10-Q filings found")
                return {}

            logger.info(f"[{ticker}] Found {len(filings)} filings (10-K/10-Q) for extraction")

            # Initialize result lists
            revenue_quarterly = []
            eps_quarterly = []
            net_income_quarterly = []
            cash_flow_quarterly = []
            cf_ytd_staging = []
            debt_to_equity_quarterly = []
            shares_outstanding_quarterly = []
            shareholder_equity_quarterly = []
            filings_metadata = []

            # Process each filing
            for filing in filings:
                try:
                    # Get XBRL data
                    xbrl = filing.xbrl()
                    if not xbrl:
                        logger.debug(f"[{ticker}] No XBRL data for filing {filing.filing_date}")
                        continue

                    statements = xbrl.statements

                    # Get fiscal period info from cover page
                    cover = statements.cover_page()
                    cover_df = cover.to_dataframe() if cover else None

                    # Extract fiscal year and quarter
                    fiscal_year = None
                    fiscal_quarter = None
                    fiscal_end = None

                    if cover_df is not None and 'label' in cover_df.columns:
                        # Find DocumentFiscalYearFocus and DocumentFiscalPeriodFocus
                        for idx, row in cover_df.iterrows():
                            label = row.get('label', '')
                            if 'Fiscal Year' in label or 'Document Fiscal Year' in label:
                                # Get the value from the first data column
                                data_cols = [col for col in cover_df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                                if data_cols:
                                    fiscal_year = row.get(data_cols[0])
                                    if fiscal_year and isinstance(fiscal_year, str):
                                        try:
                                            fiscal_year = int(fiscal_year)
                                        except:
                                            pass
                            elif 'Fiscal Period' in label or 'Document Fiscal Period' in label:
                                data_cols = [col for col in cover_df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                                if data_cols:
                                    fiscal_quarter = row.get(data_cols[0])
                            elif 'Document Period End Date' in label:
                                data_cols = [col for col in cover_df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                                if data_cols:
                                    fiscal_end = row.get(data_cols[0])

                    # Fallback for edgartools 5.x: cover page uses standard_concept column,
                    # the fiscal period date lives in the column header rather than cell values.
                    if cover_df is not None and not fiscal_end:
                        date_col = self._first_date_column(cover_df)
                        if date_col:
                            fiscal_end = date_col
                            if not fiscal_year:
                                try:
                                    fiscal_year = int(date_col[:4])
                                except (ValueError, TypeError):
                                    pass

                    # Capture filing metadata
                    filings_metadata.append({
                        'accession_number': filing.accession_number,
                        'form': filing.form,
                        'date': filing.filing_date
                    })

                    # Fallback: extract from income statement column name if not in cover page
                    if not fiscal_year or not fiscal_quarter:
                        # 10-K is always Q4
                        if filing.form == '10-K':
                            fiscal_quarter = 'Q4'
                            # Use filing year if year focus is missing (usually filing year - 1)
                            # But wait, we try to get it from income statement below if possible

                        # Try to get fiscal_end from income statement column
                        income = statements.income_statement()
                        if income:
                            income_df = income.to_dataframe()
                            if 'label' in income_df.columns:
                                quarterly_cols = [col for col in income_df.columns if isinstance(col, str) and '(Q' in col]
                                if quarterly_cols:
                                    quarterly_col = quarterly_cols[0]
                                    # Extract fiscal_end from column name like "2025-09-30 (Q3)"
                                    if '-' in quarterly_col:
                                        fiscal_end = quarterly_col.split(' ')[0]
                                        # Extract year from fiscal_end
                                        fiscal_year = int(fiscal_end[:4])

                                        # Calculate fiscal quarter based on fiscal year end
                                        # We need to determine the company's fiscal year end month
                                        # Look for the most recent 10-K to determine fiscal year end
                                        try:
                                            tenk_filings = company.get_filings(form="10-K").head(1)
                                            if tenk_filings and len(tenk_filings) > 0:
                                                tenk_filing = tenk_filings[0]
                                                tenk_xbrl = tenk_filing.xbrl()
                                                if tenk_xbrl:
                                                    tenk_income = tenk_xbrl.statements.income_statement()
                                                    if tenk_income:
                                                        tenk_df = tenk_income.to_dataframe()
                                                        # Find annual column (no Q in name)
                                                        annual_cols = [col for col in tenk_df.columns if isinstance(col, str) and '-' in col and '(Q' not in col and col != 'level']
                                                        if annual_cols:
                                                            # Get fiscal year end date from 10-K
                                                            fye_date = annual_cols[0]  # e.g., "2024-06-30"
                                                            fye_month = int(fye_date[5:7])  # Extract month

                                                            # Calculate fiscal quarter based on period end month
                                                            period_end_month = int(fiscal_end[5:7])

                                                            # Calculate months from fiscal year end
                                                            # Fiscal Q1 = 1-3 months after FYE
                                                            # Fiscal Q2 = 4-6 months after FYE
                                                            # Fiscal Q3 = 7-9 months after FYE
                                                            # Fiscal Q4 = 10-12 months after FYE (ends at FYE)

                                                            months_from_fye = (period_end_month - fye_month) % 12
                                                            if months_from_fye == 0:
                                                                months_from_fye = 12  # Period ending at FYE is Q4

                                                            if months_from_fye <= 3:
                                                                fiscal_quarter = "Q1"
                                                            elif months_from_fye <= 6:
                                                                fiscal_quarter = "Q2"
                                                            elif months_from_fye <= 9:
                                                                fiscal_quarter = "Q3"
                                                            else:
                                                                fiscal_quarter = "Q4"

                                                            logger.debug(f"[{ticker}] Calculated fiscal quarter: FYE month={fye_month}, period_end month={period_end_month}, months_from_fye={months_from_fye}, fiscal_quarter={fiscal_quarter}")
                                        except Exception as e:
                                            logger.debug(f"[{ticker}] Could not determine fiscal year end: {e}")
                                            # Do not use quarterly_col here, it is not defined yet

                    # Extract from Income Statement
                    # Always fetch the income statement for data extraction
                    income = statements.income_statement()

                    if income:
                        # Use new edgartools 5.x compatible extraction via get_raw_data()
                        extracted = self._extract_quarterly_from_raw_xbrl(
                            ticker, income, fiscal_year, fiscal_quarter
                        )

                        # Update fiscal info from extraction if not already set
                        if not fiscal_year and extracted['fiscal_year']:
                            fiscal_year = extracted['fiscal_year']
                        if not fiscal_quarter and extracted['fiscal_quarter']:
                            fiscal_quarter = extracted['fiscal_quarter']
                        if not fiscal_end and extracted['fiscal_end']:
                            fiscal_end = extracted['fiscal_end']

                        # Store extracted values
                        if extracted['revenue'] and extracted['revenue'] > 0 and fiscal_year and fiscal_quarter:
                            revenue_quarterly.append({
                                'year': fiscal_year,
                                'quarter': fiscal_quarter,
                                'revenue': extracted['revenue'],
                                'fiscal_end': fiscal_end
                            })

                        if extracted['net_income'] is not None and fiscal_year and fiscal_quarter:
                            net_income_quarterly.append({
                                'year': fiscal_year,
                                'quarter': fiscal_quarter,
                                'net_income': extracted['net_income'],
                                'fiscal_end': fiscal_end
                            })

                        if extracted['eps'] is not None and fiscal_year and fiscal_quarter:
                            eps_quarterly.append({
                                'year': fiscal_year,
                                'quarter': fiscal_quarter,
                                'eps': extracted['eps'],
                                'fiscal_end': fiscal_end
                            })

                        # Skip the old to_dataframe based extraction below
                        # (Balance sheet and cash flow extraction follows)


                    # Extract from Balance Sheet
                    balance_sheet = statements.balance_sheet()
                    if balance_sheet:
                        bs_df = balance_sheet.to_dataframe()

                        if 'label' in bs_df.columns:
                            # Find quarterly column
                            date_col = self._first_date_column(bs_df)
                            quarterly_cols = [date_col] if date_col else []

                            if quarterly_cols:
                                quarterly_col = quarterly_cols[0]

                                # Extract Total Debt
                                debt_rows = bs_df[bs_df['label'].str.contains('Debt', case=False, na=False) &
                                                 bs_df['label'].str.contains('Total', case=False, na=False)]

                                total_debt = None
                                for idx in range(len(debt_rows)):
                                    debt_row = debt_rows.iloc[idx]
                                    if 'abstract' in bs_df.columns and debt_row.get('abstract', False):
                                        continue
                                    debt = debt_row[quarterly_col]
                                    if isinstance(debt, str):
                                        if debt.strip() == '':
                                            continue
                                        try:
                                            debt = float(debt.replace(',', ''))
                                        except:
                                            continue
                                    if debt and debt > 0:
                                        total_debt = debt
                                        break

                                # Extract Shareholder Equity
                                equity_rows = bs_df[bs_df['label'].str.contains('Equity', case=False, na=False) &
                                                   (bs_df['label'].str.contains('Stockholders', case=False, na=False) |
                                                    bs_df['label'].str.contains('Shareholders', case=False, na=False) |
                                                    bs_df['label'].str.contains('Total Equity', case=False, na=False))]

                                shareholder_equity = None
                                for idx in range(len(equity_rows)):
                                    equity_row = equity_rows.iloc[idx]
                                    if 'abstract' in bs_df.columns and equity_row.get('abstract', False):
                                        continue
                                    equity = equity_row[quarterly_col]
                                    if isinstance(equity, str):
                                        if equity.strip() == '':
                                            continue
                                        try:
                                            equity = float(equity.replace(',', ''))
                                        except:
                                            continue
                                    if equity and equity > 0:
                                        shareholder_equity = equity
                                        shareholder_equity_quarterly.append({
                                            'year': fiscal_year,
                                            'quarter': fiscal_quarter,
                                            'shareholder_equity': equity,
                                            'fiscal_end': fiscal_end
                                        })
                                        break

                                # Calculate Debt/Equity if both available
                                if total_debt is not None and shareholder_equity is not None and shareholder_equity > 0:
                                    debt_to_equity_quarterly.append({
                                        'year': fiscal_year,
                                        'quarter': fiscal_quarter,
                                        'debt_to_equity': total_debt / shareholder_equity,
                                        'fiscal_end': fiscal_end
                                    })

                                # Extract Shares Outstanding
                                shares_rows = bs_df[bs_df['label'].str.contains('Shares', case=False, na=False) &
                                                   bs_df['label'].str.contains('Outstanding', case=False, na=False)]

                                for idx in range(len(shares_rows)):
                                    shares_row = shares_rows.iloc[idx]
                                    if 'abstract' in bs_df.columns and shares_row.get('abstract', False):
                                        continue
                                    shares = shares_row[quarterly_col]
                                    if isinstance(shares, str):
                                        if shares.strip() == '':
                                            continue
                                        try:
                                            shares = float(shares.replace(',', ''))
                                        except:
                                            continue
                                    if shares and shares > 0:
                                        shares_outstanding_quarterly.append({
                                            'year': fiscal_year,
                                            'quarter': fiscal_quarter,
                                            'shares': shares,
                                            'fiscal_end': fiscal_end
                                        })
                                        break

                    # Extract from Cash Flow Statement using get_raw_data() for edgartools 5.x
                    cashflow = statements.cashflow_statement()
                    if cashflow:
                        try:
                            cf_raw = cashflow.get_raw_data()
                        except Exception as e:
                            logger.debug(f"[{ticker}] Could not get CF raw data: {e}")
                            cf_raw = None

                        if cf_raw:
                            # CF summary totals (OCF, capex) always use YTD period keys,
                            # even when individual adjustment items have discrete keys.
                            # Always stage YTD values for post-loop discrete subtraction.
                            ytd_key = None
                            if fiscal_end:
                                for item in cf_raw:
                                    if not item.get('has_values') or item.get('is_abstract'):
                                        continue
                                    for pk in item.get('values', {}).keys():
                                        if pk.startswith('duration_') and pk.endswith(f'_{fiscal_end}'):
                                            ytd_key = pk
                                            break
                                    if ytd_key:
                                        break

                            if ytd_key:
                                ocf_ytd, capex_ytd = self._extract_cf_from_raw_data(cf_raw, ytd_key)
                                if ocf_ytd is not None or capex_ytd is not None:
                                    cf_ytd_staging.append({
                                        'year': fiscal_year,
                                        'quarter': fiscal_quarter,
                                        'fiscal_end': fiscal_end,
                                        'ocf_ytd': ocf_ytd,
                                        'capex_ytd': capex_ytd,
                                    })
                                    logger.debug(f"[{ticker}] CF YTD staged: OCF={ocf_ytd}, capex={capex_ytd}, q={fiscal_quarter}")

                except Exception as e:
                    logger.debug(f"[{ticker}] Error processing filing {filing.filing_date}: {e}")
                    continue

            if cf_ytd_staging:
                discrete_cf = self._compute_discrete_cf(cf_ytd_staging)
                cash_flow_quarterly.extend(discrete_cf)
                logger.debug(f"[{ticker}] CF YTD staging: {len(cf_ytd_staging)} entries → {len(discrete_cf)} discrete")

            logger.info(f"[{ticker}] Extracted from 10-Q filings: {len(revenue_quarterly)} revenue, {len(eps_quarterly)} EPS, {len(net_income_quarterly)} NI, {len(cash_flow_quarterly)} CF, {len(debt_to_equity_quarterly)} D/E, {len(shares_outstanding_quarterly)} shares, {len(shareholder_equity_quarterly)} equity")

            return {
                'revenue_quarterly': revenue_quarterly,
                'eps_quarterly': eps_quarterly,
                'net_income_quarterly': net_income_quarterly,
                'cash_flow_quarterly': cash_flow_quarterly,
                'debt_to_equity_quarterly': debt_to_equity_quarterly,
                'shares_outstanding_quarterly': shares_outstanding_quarterly,
                'shareholder_equity_quarterly': shareholder_equity_quarterly,
                'filings_metadata': filings_metadata
            }

        except Exception as e:
            logger.error(f"[{ticker}] Error in get_quarterly_financials_from_filings: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _fetch_fundamentals_from_db(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Reconstruct fundamentals from parsed earnings_history in DB.
        Bypasses raw company_facts fetch if we already have the data.
        """
        try:
            # Check for basic metrics first
            metrics = self.db.get_stock_metrics(ticker)
            if not metrics:
                return None

            # Get annual and quarterly history
            annual_rows = self.db.get_earnings_history(ticker, period_type='annual')
            quarterly_rows = self.db.get_earnings_history(ticker, period_type='quarterly')

            if not annual_rows:
                return None

            # Helper to map DB rows to dicts
            def map_rows(rows, val_key, out_key_val='val'):
                return [{
                    'year': r['year'],
                    'quarter': r.get('period') if r.get('period') not in ['annual', None] else None,
                    out_key_val: r.get(val_key),
                    'fiscal_end': r.get('fiscal_end')
                } for r in rows if r.get(val_key) is not None]

            # Reconstruct lists
            eps_history = [{
                'year': r['year'],
                'eps': r['eps'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('eps') is not None]

            revenue_history = [{
                'year': r['year'],
                'revenue': r['revenue'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('revenue') is not None]

            net_income_annual = [{
                'year': r['year'],
                'net_income': r['net_income'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('net_income') is not None]

            # Quarterly lists
            net_income_quarterly = map_rows(quarterly_rows, 'net_income', 'net_income')
            revenue_quarterly = map_rows(quarterly_rows, 'revenue', 'revenue')
            eps_quarterly = map_rows(quarterly_rows, 'eps', 'eps')
            cash_flow_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'operating_cash_flow': r['operating_cash_flow'],
                'capital_expenditures': r['capital_expenditures'],
                'free_cash_flow': r['free_cash_flow'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('operating_cash_flow') is not None]

            # Other annual histories
            cash_flow_history = [{
                'year': r['year'],
                'operating_cash_flow': r['operating_cash_flow'],
                'capital_expenditures': r['capital_expenditures'],
                'free_cash_flow': r['free_cash_flow'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('operating_cash_flow') is not None]

            debt_to_equity_history = [{
                'year': r['year'],
                'debt_to_equity': r['debt_to_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('debt_to_equity') is not None]

            debt_to_equity_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'debt_to_equity': r['debt_to_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('debt_to_equity') is not None]

            shareholder_equity_history = [{
                'year': r['year'],
                'shareholder_equity': r['shareholder_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('shareholder_equity') is not None]

            shareholder_equity_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'shareholder_equity': r['shareholder_equity'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('shareholder_equity') is not None]

            shares_outstanding_history = [{
                'year': r['year'],
                'shares': r['shares_outstanding'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('shares_outstanding') is not None]

            shares_outstanding_quarterly = [{
                'year': r['year'],
                'quarter': r['period'],
                'shares': r['shares_outstanding'],
                'fiscal_end': r['fiscal_end']
            } for r in quarterly_rows if r.get('shares_outstanding') is not None]

            dividend_history = [{
                'year': r['year'],
                'amount': r['dividend_amount'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('dividend_amount') is not None]

            cash_equivalents_history = [{
                'year': r['year'],
                'cash_and_cash_equivalents': r['cash_and_cash_equivalents'],
                'fiscal_end': r['fiscal_end']
            } for r in annual_rows if r.get('cash_and_cash_equivalents') is not None]

            # Most recent debt_to_equity
            current_de = metrics.get('debt_to_equity')

            # CIK
            cik = self.get_cik_for_ticker(ticker)

            return {
                'ticker': ticker,
                'cik': cik,
                'company_name': metrics.get('company_name', ''),
                'eps_history': eps_history,
                'calculated_eps_history': eps_history, # Use same as reported
                'net_income_annual': net_income_annual,
                'shareholder_equity_history': shareholder_equity_history,
                'shareholder_equity_quarterly': shareholder_equity_quarterly,
                'cash_equivalents_history': cash_equivalents_history,
                'shares_outstanding_history': shares_outstanding_history,
                'net_income_quarterly': net_income_quarterly,
                'revenue_quarterly': revenue_quarterly,
                'eps_quarterly': eps_quarterly,
                'calculated_eps_quarterly': eps_quarterly,
                'cash_flow_quarterly': cash_flow_quarterly,
                'debt_to_equity_quarterly': debt_to_equity_quarterly,
                'shares_outstanding_quarterly': shares_outstanding_quarterly,
                'revenue_history': revenue_history,
                'debt_to_equity': current_de,
                'debt_to_equity_history': debt_to_equity_history,
                'cash_flow_history': cash_flow_history,
                'dividend_history': dividend_history,
                'interest_expense': metrics.get('interest_expense'),
                'effective_tax_rate': metrics.get('effective_tax_rate'),
                'company_facts': {} # Emulate empty raw data
            }

        except Exception as e:
            logger.warning(f"[{ticker}] Failed to reconstruct fundamentals from DB: {e}")
            return None


    def _needs_quarterly_refresh(self, ticker: str) -> bool:
        """
        Check if we need to refresh quarterly data from 10-Q filings.
        Returns True if the cached quarterly data is missing the most recent quarter.

        Args:
            ticker: Stock ticker symbol

        Returns:
            True if quarterly data needs refresh, False if cached data is current
        """
        if not self.db:
            return True  # No DB means we need to fetch

        try:
            from datetime import datetime, timedelta

            # Get most recent quarterly earnings from DB
            quarterly_rows = self.db.get_earnings_history(ticker, period_type='quarterly')
            if not quarterly_rows:
                logger.info(f"[{ticker}] No quarterly data in DB - needs refresh")
                return True

            # Find the most recent quarter in DB
            most_recent = max(quarterly_rows, key=lambda r: (r['year'], r.get('period', 'Q1')))
            db_year = most_recent['year']
            db_quarter = most_recent.get('period', 'Q1')  # e.g., 'Q1', 'Q2', 'Q3', 'Q4'
            db_quarter_num = int(db_quarter.replace('Q', ''))

            # Get fiscal year end from most recent annual data to determine fiscal calendar
            annual_rows = self.db.get_earnings_history(ticker, period_type='annual')
            if not annual_rows:
                logger.info(f"[{ticker}] No annual data to determine fiscal year end - needs refresh")
                return True

            # Get fiscal year end (e.g., '2024-12-31')
            most_recent_annual = max(annual_rows, key=lambda r: r['year'])
            fiscal_end_str = most_recent_annual.get('fiscal_end')
            if not fiscal_end_str:
                logger.info(f"[{ticker}] No fiscal_end date available - needs refresh")
                return True

            # Parse fiscal year end to get the month/day (e.g., Dec 31 -> 12-31)
            fiscal_end_date = datetime.strptime(fiscal_end_str, '%Y-%m-%d')
            fiscal_month = fiscal_end_date.month
            fiscal_day = fiscal_end_date.day

            # Calculate what the expected current quarter should be
            today = datetime.now()

            # Determine the current fiscal year based on fiscal year end
            if (today.month, today.day) >= (fiscal_month, fiscal_day):
                current_fiscal_year = today.year
            else:
                current_fiscal_year = today.year - 1

            # Calculate quarter end dates for this fiscal year
            # Fiscal Q4 ends on fiscal_end (e.g., Dec 31)
            # Fiscal Q3 ends 3 months before
            # Fiscal Q2 ends 6 months before
            # Fiscal Q1 ends 9 months before
            q4_end = datetime(current_fiscal_year, fiscal_month, fiscal_day)
            q3_end = q4_end - timedelta(days=90)  # Approximate
            q2_end = q3_end - timedelta(days=90)
            q1_end = q2_end - timedelta(days=90)

            # Determine which quarter we should have data for
            # Companies typically file 10-Q within 45 days after quarter end
            filing_delay = timedelta(days=45)

            if today >= q4_end + filing_delay:
                expected_quarter = 4
                expected_year = current_fiscal_year
            elif today >= q3_end + filing_delay:
                expected_quarter = 3
                expected_year = current_fiscal_year
            elif today >= q2_end + filing_delay:
                expected_quarter = 2
                expected_year = current_fiscal_year
            elif today >= q1_end + filing_delay:
                expected_quarter = 1
                expected_year = current_fiscal_year
            else:
                # We're before Q1 filing, so expect Q4 of previous fiscal year
                expected_quarter = 4
                expected_year = current_fiscal_year - 1

            # Check if we have the expected quarter in DB
            if db_year < expected_year or (db_year == expected_year and db_quarter_num < expected_quarter):
                logger.info(f"[{ticker}] Quarterly data stale: DB has {db_year} Q{db_quarter_num}, expected {expected_year} Q{expected_quarter} - needs refresh")
                return True

            logger.info(f"[{ticker}] Quarterly data current: DB has {db_year} Q{db_quarter_num}, expected {expected_year} Q{expected_quarter} - no refresh needed")
            return False

        except Exception as e:
            logger.warning(f"[{ticker}] Error checking quarterly freshness: {e} - will refresh to be safe")
            return True


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
            return None

        # Try to fetch from DB first (earnings_history)
        # This avoids redundant SEC API calls since company_facts table is unused
        has_cached_data = False
        db_fundamentals = None
        if self.db:
            db_fundamentals = self._fetch_fundamentals_from_db(ticker)
            if db_fundamentals:
                has_cached_data = True
                # We have cached data, but check if quarterly data needs updating
                needs_quarterly_refresh = self._needs_quarterly_refresh(ticker)
                if not needs_quarterly_refresh:
                    logger.info(f"[{ticker}] Returning fundamentals from earnings_history DB cache (quarterly data current)")
                    return db_fundamentals
                else:
                    logger.info(f"[{ticker}] DB cache exists but quarterly data is stale - will refresh recent quarters only")

        # Fetch company facts (skip if we have cached historical data and only need quarterly refresh)
        company_facts = None
        if not has_cached_data:
            company_facts = self.fetch_company_facts(cik)
            if not company_facts:
                return None

        # Parse all fundamental data (skip if using cached data)
        if not has_cached_data:
            eps_history = self.parse_eps_history(company_facts)
            revenue_history = self.parse_revenue_history(company_facts)
            debt_to_equity = self.parse_debt_to_equity(company_facts)
            debt_to_equity_history = self.parse_debt_to_equity_history(company_facts)
            shareholder_equity_history = self.parse_shareholder_equity_history(company_facts)
            # shareholder_equity_quarterly now comes from 10-Q parsing above
            cash_equivalents_history = self.parse_cash_equivalents_history(company_facts)
            cash_flow_history = self.parse_cash_flow_history(company_facts)

            # Extract Interest Expense and Tax Rate
            interest_expense = self.parse_interest_expense(company_facts)
            effective_tax_rate = self.parse_effective_tax_rate(company_facts)

            # Calculate split-adjusted EPS from Net Income / Shares Outstanding
            calculated_eps_history = self.calculate_split_adjusted_annual_eps_history(company_facts)

            # Extract Net Income directly for storage
            net_income_annual = self.parse_net_income_history(company_facts)
        else:
            # Use data from cached DB fundamentals
            logger.info(f"[{ticker}] Using historical data from DB cache, only refreshing quarterly")
            eps_history = db_fundamentals.get('eps_history', [])
            revenue_history = db_fundamentals.get('revenue_history', [])
            debt_to_equity = db_fundamentals.get('debt_to_equity')
            debt_to_equity_history = db_fundamentals.get('debt_to_equity_history', [])
            shareholder_equity_history = db_fundamentals.get('shareholder_equity_history', [])
            cash_equivalents_history = db_fundamentals.get('cash_equivalents_history', [])
            cash_flow_history = db_fundamentals.get('cash_flow_history', [])
            interest_expense = db_fundamentals.get('interest_expense')
            effective_tax_rate = db_fundamentals.get('effective_tax_rate')
            calculated_eps_history = db_fundamentals.get('calculated_eps_history', eps_history)
            net_income_annual = db_fundamentals.get('net_income_annual', [])


        # HYBRID APPROACH: Combine 10-Q parsing (accurate recent data) with company_facts (complete historical data)
        # - Use 10-Q parsing for last 8 quarters (most accurate, handles fiscal quarters correctly)
        # - Use company_facts for historical data (complete coverage, even if slightly outdated)
        logger.info(f"[{ticker}] Extracting quarterly data using hybrid approach...")

        # 1. Get recent quarters from 10-K/10-Q filings (last 8 quarters, ~2 years)
        logger.info(f"[{ticker}] Fetching recent 8 quarters from 10-K/10-Q filings...")
        quarterly_filing_data = self.get_quarterly_financials_from_filings(ticker, num_quarters=8)

        # NOTE: The cumulative revenue fix below was removed - the root cause was that
        # income = statements.income_statement() was not being called when fiscal info
        # was found from the cover page. This has been fixed above.


        # 2. Get historical quarters from company_facts (or from DB cache)
        if not has_cached_data:
            logger.info(f"[{ticker}] Fetching historical quarterly data from company_facts...")
            historical_revenue_quarterly = self.parse_quarterly_revenue_history(company_facts)
            historical_net_income_quarterly = self.parse_quarterly_net_income_history(company_facts)
            historical_cash_flow_quarterly = self.parse_quarterly_cash_flow_history(company_facts)
            historical_debt_to_equity_quarterly = self.parse_quarterly_debt_to_equity_history(company_facts)
            historical_shares_outstanding_quarterly = self.parse_quarterly_shares_outstanding_history(company_facts)
            historical_shareholder_equity_quarterly = self.parse_quarterly_shareholder_equity_history(company_facts)
        else:
            logger.info(f"[{ticker}] Using historical quarterly data from DB cache...")
            historical_revenue_quarterly = db_fundamentals.get('revenue_quarterly', [])
            historical_net_income_quarterly = db_fundamentals.get('net_income_quarterly', [])
            historical_cash_flow_quarterly = db_fundamentals.get('cash_flow_quarterly', [])
            historical_debt_to_equity_quarterly = db_fundamentals.get('debt_to_equity_quarterly', [])
            historical_shares_outstanding_quarterly = db_fundamentals.get('shares_outstanding_quarterly', [])
            historical_shareholder_equity_quarterly = db_fundamentals.get('shareholder_equity_quarterly', [])

        # 3. Merge: 10-Q data takes precedence for recent quarters
        def merge_quarterly_data(recent_data, historical_data):
            """Merge recent 10-Q data with historical company_facts data, 10-Q takes precedence"""
            # Create dict keyed by (year, quarter) for recent data
            recent_by_key = {(e['year'], e['quarter']): e for e in recent_data}

            # Create dict for historical data
            historical_by_key = {(e['year'], e['quarter']): e for e in historical_data}

            # Merge: start with historical, then overwrite with recent
            merged = dict(historical_by_key)
            merged.update(recent_by_key)

            # Convert back to list and sort by date (newest first)
            result = list(merged.values())
            result.sort(key=lambda x: (x['year'], x['quarter']), reverse=True)
            return result

        # Merge each metric
        revenue_quarterly = merge_quarterly_data(
            quarterly_filing_data.get('revenue_quarterly', []),
            historical_revenue_quarterly or []
        )

        net_income_quarterly = merge_quarterly_data(
            quarterly_filing_data.get('net_income_quarterly', []),
            historical_net_income_quarterly or []
        )

        eps_quarterly = quarterly_filing_data.get('eps_quarterly', [])  # Only from 10-Q (more accurate)

        cash_flow_quarterly = merge_quarterly_data(
            quarterly_filing_data.get('cash_flow_quarterly', []),
            historical_cash_flow_quarterly or []
        )

        debt_to_equity_quarterly = merge_quarterly_data(
            quarterly_filing_data.get('debt_to_equity_quarterly', []),
            historical_debt_to_equity_quarterly or []
        )

        shares_outstanding_quarterly = merge_quarterly_data(
            quarterly_filing_data.get('shares_outstanding_quarterly', []),
            historical_shares_outstanding_quarterly or []
        )

        shareholder_equity_quarterly = merge_quarterly_data(
            quarterly_filing_data.get('shareholder_equity_quarterly', []),
            historical_shareholder_equity_quarterly or []
        )

        logger.info(f"[{ticker}] Hybrid merge complete: {len(revenue_quarterly)} revenue quarters, {len(net_income_quarterly)} NI quarters, {len(eps_quarterly)} EPS quarters")

        # Parse data that depends on company_facts only if we fetched it
        if not has_cached_data and company_facts:
            # Keep calculated EPS from company_facts as fallback
            calculated_eps_quarterly = self.calculate_quarterly_eps_history(company_facts)

            # Extract shares outstanding history (annual)
            shares_outstanding_history = self.parse_shares_outstanding_history(company_facts)

            # Parse dividend history
            dividend_history = self.parse_dividend_history(company_facts)

            company_name = company_facts.get('entityName', '')
            raw_facts = company_facts
        else:
            # Use data from cached DB fundamentals or defaults
            calculated_eps_quarterly = db_fundamentals.get('calculated_eps_quarterly', []) if db_fundamentals else []
            shares_outstanding_history = db_fundamentals.get('shares_outstanding_history', []) if db_fundamentals else []
            dividend_history = db_fundamentals.get('dividend_history', []) if db_fundamentals else []
            company_name = db_fundamentals.get('company_name', '') if db_fundamentals else ''
            raw_facts = {}

        logger.info(f"[{ticker}] EDGAR fetch complete: {len(eps_history or [])} EPS years, {len(calculated_eps_history or [])} calculated EPS years, {len(net_income_annual or [])} annual NI, {len(net_income_quarterly or [])} quarterly NI, {len(revenue_quarterly or [])} quarterly Rev, {len(eps_quarterly or [])} quarterly EPS, {len(calculated_eps_quarterly or [])} calculated Q-EPS, {len(cash_flow_quarterly or [])} quarterly CF, {len(revenue_history or [])} revenue years, {len(debt_to_equity_history or [])} D/E years, {len(debt_to_equity_quarterly)} quarterly D/E, {len(shareholder_equity_history or [])} Equity years, {len(shareholder_equity_quarterly)} Quarterly Equity, {len(cash_equivalents_history or [])} Cash years, {len(shares_outstanding_history or [])} shares outstanding years, {len(cash_flow_history or [])} cash flow years, {len(dividend_history or [])} dividend entries, current D/E: {debt_to_equity}")

        fundamentals = {
            'ticker': ticker,
            'cik': cik,
            'company_name': company_name,
            'eps_history': eps_history,
            'calculated_eps_history': calculated_eps_history,
            'net_income_annual': net_income_annual,
            'shareholder_equity_history': shareholder_equity_history,
            'shareholder_equity_quarterly': shareholder_equity_quarterly,
            'cash_equivalents_history': cash_equivalents_history,
            'shares_outstanding_history': shares_outstanding_history,
            'net_income_quarterly': net_income_quarterly,
            'revenue_quarterly': revenue_quarterly,
            'eps_quarterly': eps_quarterly,
            'calculated_eps_quarterly': calculated_eps_quarterly,
            'cash_flow_quarterly': cash_flow_quarterly,
            'debt_to_equity_quarterly': debt_to_equity_quarterly,
            'shares_outstanding_quarterly': shares_outstanding_quarterly,
            'revenue_history': revenue_history,
            'debt_to_equity': debt_to_equity,
            'debt_to_equity_history': debt_to_equity_history,
            'cash_flow_history': cash_flow_history,
            'dividend_history': dividend_history,
            'interest_expense': interest_expense,
            'effective_tax_rate': effective_tax_rate,
            'company_facts': raw_facts
        }

        return fundamentals

    def merge_quarterly_data(self, recent_data, historical_data):
        """Merge recent 10-Q data with historical company_facts data, 10-Q takes precedence"""
        # Create dict keyed by (year, quarter) for recent data
        recent_by_key = {(e['year'], e['quarter']): e for e in recent_data}

        # Create dict for historical data
        historical_by_key = {(e['year'], e['quarter']): e for e in historical_data}

        # Merge: start with historical, then overwrite with recent
        merged = dict(historical_by_key)
        merged.update(recent_by_key)

        # Convert back to list and sort by date (newest first)
        result = list(merged.values())
        result.sort(key=lambda x: (x['year'], x['quarter']), reverse=True)
        return result
