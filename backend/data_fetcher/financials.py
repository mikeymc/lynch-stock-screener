# ABOUTME: Mixin for financial data operations including debt/equity, cash flow, and dividends
# ABOUTME: Handles backfilling from yfinance and processing 8-K Item 2.02 earnings events

import yfinance as yf
import logging
from typing import Dict, Any, Optional, List
import pandas as pd
from yfinance_rate_limiter import with_timeout_and_retry

logger = logging.getLogger(__name__)


class FinancialsMixin:
    def _backfill_debt_to_equity(self, symbol: str, years: List[int]):
        """
        Backfill missing debt-to-equity data from yfinance balance sheets

        Args:
            symbol: Stock symbol
            years: List of years that need D/E data
        """
        try:
            balance_sheet = self._get_yf_balance_sheet(symbol)

            if balance_sheet is None or balance_sheet.empty:
                logger.warning(f"[{symbol}] No balance sheet data available from yfinance")
                return

            de_filled_count = 0
            for col in balance_sheet.columns:
                year = col.year if hasattr(col, 'year') else None
                if year and year in years:
                    debt_to_equity, _ = self._calculate_debt_to_equity(balance_sheet, col)
                    if debt_to_equity is not None:
                        # Update the existing record with D/E data
                        conn = self.db.get_connection()
                        try:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE earnings_history
                                SET debt_to_equity = %s
                                WHERE symbol = %s AND year = %s AND period = 'annual'
                            """, (debt_to_equity, symbol, year))
                            conn.commit()
                            de_filled_count += 1
                            logger.debug(f"[{symbol}] Backfilled D/E for {year}: {debt_to_equity:.2f}")
                        finally:
                            self.db.return_connection(conn)

            if de_filled_count > 0:
                logger.info(f"[{symbol}] Successfully backfilled D/E for {de_filled_count}/{len(years)} years from yfinance")
            else:
                logger.debug(f"[{symbol}] Could not backfill any D/E data from yfinance")

        except Exception as e:
            logger.error(f"[{symbol}] Error backfilling D/E data: {type(e).__name__}: {e}")

    def _calculate_debt_to_equity(self, balance_sheet, col) -> tuple[Optional[float], Optional[float]]:
        """
        Calculate debt-to-equity ratio from balance sheet data

        Args:
            balance_sheet: pandas DataFrame containing balance sheet data
            col: column/date to extract data from

        Returns:
            Tuple of (debt_to_equity_ratio, total_debt) or (None, None) if data unavailable
        """
        try:
            # Try to get Total Debt (preferred) or Total Liabilities
            debt_or_liab = None
            equity = None

            # List of possible keys for Debt (preferred)
            # 'Total Debt' is explicit interest-bearing debt
            # 'Total Liabilities' includes everything (payables, deferred tax, etc.) and gives a much higher ratio
            debt_keys = [
                'Total Debt',
                'Total Liabilities Net Minority Interest',
                'Total Liab',
                'Total Liabilities',
                'Total Liabilities Net Minority Interest'
            ]

            for key in debt_keys:
                if key in balance_sheet.index:
                    debt_or_liab = balance_sheet.loc[key, col]
                    if pd.notna(debt_or_liab):
                        logger.debug(f"Using {key} for D/E calculation: {debt_or_liab}")
                        break

            # List of possible keys for Equity
            equity_keys = [
                'Stockholders Equity',
                'Total Stockholder Equity',
                'Total Equity Gross Minority Interest',
                'Common Stock Equity'
            ]

            for key in equity_keys:
                if key in balance_sheet.index:
                    equity = balance_sheet.loc[key, col]
                    break

            # Calculate D/E ratio if both values are available and valid
            if pd.notna(debt_or_liab) and pd.notna(equity) and equity != 0:
                ratio = float(debt_or_liab / equity)
                total_debt = float(debt_or_liab)
                return (ratio, total_debt)

            return (None, None)
        except Exception as e:
            logger.debug(f"Error calculating D/E ratio: {e}")
            return (None, None)

    def process_item_202(self, symbol: str, event: Dict[str, Any]):
        """
        Process an 8-K Item 2.02 event to extract earnings data and gap-fill the database.

        Args:
            symbol: Stock symbol
            event: The 8-K event dictionary (must contain 'content_text' and 'filing_date')
        """
        try:
            content = event.get('content_text')
            filing_date = event.get('filing_date')

            if not content:
                logger.warning(f"[{symbol}] Item 2.02 event missing content, skipping extraction.")
                return

            # 1. Extract Data
            logger.info(f"[{symbol}] Extracting earnings from Item 2.02 (Date: {filing_date})...")
            # filng_date is a date object usually, convert to YYYY-MM-DD string
            filing_date_str = str(filing_date) if filing_date else None

            data = self.earnings_extractor.extract(content, filing_date=filing_date_str)

            logger.info(f"[{symbol}] Extracted: FY{data.fiscal_year} {data.quarter} - Rev: ${data.revenue:,.0f}, NI: ${data.net_income:,.0f}, EPS: ${data.eps:.2f}")

            # 2. Gap-Fill Check
            # Check if we already have data for this period (Symbol, Year, Quarter)
            # The database 'earnings_history' has a unique constraint on (symbol, year, period)
            # 'period' for quarterly is usually 'Q1', 'Q2', etc. (Stored as text? Check schema.)
            # Schema: UNIQUE(symbol, year, period)

            conn = self.db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM earnings_history
                    WHERE symbol = %s AND year = %s AND period = %s
                """, (symbol, data.fiscal_year, data.quarter))
                exists = cursor.fetchone()

                if exists:
                    logger.info(f"[{symbol}] Data for {data.fiscal_year} {data.quarter} already exists. Skipping 8-K gap-fill.")
                    return

                logger.info(f"[{symbol}] Gap-fill: Inserting 8-K earnings for {data.fiscal_year} {data.quarter}")

                 # Compute Derived Metrics
                free_cash_flow = None
                if data.operating_cash_flow is not None and data.capital_expenditures is not None:
                    # FCF = OCF - CapEx. CapEx should be positive magnitude as per prompt instruction.
                    free_cash_flow = data.operating_cash_flow - abs(data.capital_expenditures)

                debt_to_equity = None
                if data.total_debt is not None and data.shareholder_equity:
                    if data.shareholder_equity != 0:
                        debt_to_equity = data.total_debt / data.shareholder_equity

                self.db.save_earnings_history(
                    symbol=symbol,
                    year=data.fiscal_year,
                    eps=data.eps,
                    revenue=data.revenue,
                    net_income=data.net_income,
                    period=data.quarter,
                    operating_cash_flow=data.operating_cash_flow,
                    capital_expenditures=data.capital_expenditures,
                    free_cash_flow=free_cash_flow,
                    total_debt=data.total_debt,
                    shareholder_equity=data.shareholder_equity,
                    debt_to_equity=debt_to_equity,
                    shares_outstanding=data.shares_outstanding,
                    cash_and_cash_equivalents=data.cash_and_cash_equivalents,
                    dividend_amount=data.dividend_amount,
                    fiscal_end=None,
                )
            finally:
                self.db.return_connection(conn)

        except Exception as e:
            logger.error(f"[{symbol}] Error processing Item 2.02: {e}")

    def _backfill_cash_flow(self, symbol: str, years: List[int]):
        """
        Backfill missing cash flow data (OCF, CapEx, FCF) from yfinance
        """
        try:
            # We need the cashflow statement properly
            ticker = yf.Ticker(symbol)
            cashflow = ticker.cashflow

            if cashflow is None or cashflow.empty:
                logger.warning(f"[{symbol}] No cashflow data available from yfinance")
                return

            cf_filled_count = 0

            # Helper to safely get value from Series/DataFrame
            def get_val(df, keys):
                for key in keys:
                    if key in df.index:
                        return df.loc[key]
                return None

            for col in cashflow.columns:
                year = col.year if hasattr(col, 'year') else None
                if year and year in years:
                    # Extract metrics for this year
                    # Use standard yfinance keys
                    ocf = get_val(cashflow[col], ['Operating Cash Flow', 'Total Cash From Operating Activities'])
                    capex = get_val(cashflow[col], ['Capital Expenditure', 'Capital Expenditures', 'Total Capital Expenditures'])
                    fcf = get_val(cashflow[col], ['Free Cash Flow'])

                    # Prepare updates
                    updates = []
                    params = []

                    if ocf is not None and not pd.isna(ocf):
                        updates.append("operating_cash_flow = %s")
                        params.append(float(ocf))

                    if capex is not None and not pd.isna(capex):
                        updates.append("capital_expenditures = %s")
                        # yfinance usually reports CapEx as negative, which aligns with our standard
                        params.append(float(capex))

                    if fcf is not None and not pd.isna(fcf):
                        updates.append("free_cash_flow = %s")
                        params.append(float(fcf))

                    if updates:
                        conn = self.db.get_connection()
                        try:
                            cursor = conn.cursor()
                            # Construct dynamic UPDATE query
                            query = f"UPDATE earnings_history SET {', '.join(updates)} WHERE symbol = %s AND year = %s AND period = 'annual'"
                            params.extend([symbol, year])

                            cursor.execute(query, tuple(params))
                            conn.commit()
                            cf_filled_count += 1
                            logger.debug(f"[{symbol}] Backfilled Cash Flow for {year}: OCF={ocf}, CapEx={capex}, FCF={fcf}")
                        finally:
                            self.db.return_connection(conn)

            if cf_filled_count > 0:
                logger.info(f"[{symbol}] Successfully backfilled Cash Flow for {cf_filled_count}/{len(years)} years from yfinance")
        except Exception as e:
            logger.error(f"[{symbol}] Error backfilling Cash Flow data: {e}")


    @with_timeout_and_retry(timeout=30, max_retries=3, operation_name="yfinance dividends")
    def _get_yf_dividends(self, symbol: str):
        """Fetch yfinance dividends with timeout and retry protection"""
        stock = yf.Ticker(symbol)
        return stock.dividends
