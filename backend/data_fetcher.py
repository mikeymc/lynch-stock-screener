# ABOUTME: Fetches stock data using hybrid EDGAR + yfinance approach
# ABOUTME: Uses EDGAR for fundamentals, yfinance for current market data

import yfinance as yf
import logging
from typing import Dict, Any, Optional, List
from database import Database
from edgar_fetcher import EdgarFetcher
import pandas as pd

logger = logging.getLogger(__name__)


class DataFetcher:
    def __init__(self, db: Database):
        self.db = db
        self.edgar_fetcher = EdgarFetcher(user_agent="Lynch Stock Screener mikey@example.com")

    def fetch_stock_data(self, symbol: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        if not force_refresh and self.db.is_cache_valid(symbol):
            return self.db.get_stock_metrics(symbol)

        try:
            # Try fetching fundamentals from EDGAR first
            logger.info(f"[{symbol}] Attempting EDGAR fetch")
            edgar_data = self.edgar_fetcher.fetch_stock_fundamentals(symbol)

            # Fetch current market data from yfinance
            stock = yf.Ticker(symbol)
            info = stock.info

            if not info or 'symbol' not in info:
                return None

            company_name = info.get('longName', '')
            exchange = info.get('exchange', '')
            sector = info.get('sector', '')
            country = info.get('country', '')

            # Calculate IPO year from firstTradeDateMilliseconds or firstTradeDateEpochUtc
            ipo_year = None
            first_trade_millis = info.get('firstTradeDateMilliseconds')
            first_trade_epoch = info.get('firstTradeDateEpochUtc')
            if first_trade_millis:
                from datetime import datetime as dt
                ipo_year = dt.fromtimestamp(first_trade_millis / 1000).year
            elif first_trade_epoch:
                from datetime import datetime as dt
                ipo_year = dt.fromtimestamp(first_trade_epoch).year

            self.db.save_stock_basic(symbol, company_name, exchange, sector, country, ipo_year)

            # Use EDGAR debt-to-equity if available, otherwise fall back to yfinance
            debt_to_equity = None
            if edgar_data and edgar_data.get('debt_to_equity'):
                debt_to_equity = edgar_data['debt_to_equity']
            else:
                debt_to_equity_pct = info.get('debtToEquity', 0)
                debt_to_equity = debt_to_equity_pct / 100 if debt_to_equity_pct else None

            # Use yfinance for current market data (price, P/E, market cap, institutional ownership)
            # yfinance returns dividendYield already as percentage (e.g., 2.79 for 2.79%)
            dividend_yield = info.get('dividendYield')

            metrics = {
                'price': info.get('currentPrice'),
                'pe_ratio': info.get('trailingPE'),
                'market_cap': info.get('marketCap'),
                'debt_to_equity': debt_to_equity,
                'institutional_ownership': info.get('heldPercentInstitutions'),
                'revenue': info.get('totalRevenue'),
                'dividend_yield': dividend_yield
            }
            self.db.save_stock_metrics(symbol, metrics)
            # todo: this code seems to complicated. do we really need to count calculated eps?
            # Use EDGAR calculated EPS if available (≥5 years), otherwise fall back to yfinance
            if edgar_data and edgar_data.get('calculated_eps_history') and edgar_data.get('revenue_history'):
                calculated_eps_count = len(edgar_data.get('calculated_eps_history', []))
                rev_count = len(edgar_data.get('revenue_history', []))

                # calculated_eps_history already has matched years (Net Income / Shares)
                # Just check that we have revenue for those years
                calc_eps_years = {entry['year'] for entry in edgar_data.get('calculated_eps_history', [])}
                rev_years = {entry['year'] for entry in edgar_data.get('revenue_history', [])}
                matched_years = len(calc_eps_years & rev_years)

                logger.info(f"[{symbol}] EDGAR returned {calculated_eps_count} calculated EPS years, {rev_count} revenue years, {matched_years} matched")

                # Use EDGAR only if we have >= 5 matched years, otherwise fall back to yfinance
                if matched_years >= 5:
                    logger.info(f"[{symbol}] Using EDGAR Net Income ({matched_years} years)")
                    self._store_edgar_earnings(symbol, edgar_data)
                    # Fetch quarterly data from EDGAR
                    if edgar_data.get('net_income_quarterly'):
                        logger.info(f"[{symbol}] Fetching quarterly Net Income from EDGAR")
                        self._store_edgar_quarterly_earnings(symbol, edgar_data)
                    else:
                        logger.warning(f"[{symbol}] No quarterly Net Income available, falling back to yfinance for quarterly data")
                        self._fetch_quarterly_earnings(symbol, stock)
                else:
                    logger.info(f"[{symbol}] EDGAR has insufficient matched years ({matched_years} < 5). Falling back to yfinance")
                    self._fetch_and_store_earnings(symbol, stock)
            else:
                if edgar_data:
                    calculated_eps_count = len(edgar_data.get('calculated_eps_history', []))
                    rev_count = len(edgar_data.get('revenue_history', []))
                    logger.info(f"[{symbol}] Partial EDGAR data: {calculated_eps_count} calculated EPS years, {rev_count} revenue years. Falling back to yfinance")
                else:
                    logger.info(f"[{symbol}] EDGAR fetch failed. Using yfinance")
                self._fetch_and_store_earnings(symbol, stock)

            return self.db.get_stock_metrics(symbol)

        except Exception as e:
            print(f"Error fetching stock data for {symbol}: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    # todo: do we need calcualted_eps_history? can we ditch eps altogether?
    # todo: rename to _store_edgar_annual_earnings
    def _store_edgar_earnings(self, symbol: str, edgar_data: Dict[str, Any]):
        """Store earnings history from EDGAR data using Net Income"""
        # Use net_income_annual (raw Net Income from EDGAR)
        net_income_annual = edgar_data.get('net_income_annual', [])
        revenue_history = edgar_data.get('revenue_history', [])
        debt_to_equity_history = edgar_data.get('debt_to_equity_history', [])
        calculated_eps_history = edgar_data.get('calculated_eps_history', [])

        # Create mapping of year to revenue and fiscal_end for easy lookup
        revenue_by_year = {entry['year']: {'revenue': entry['revenue'], 'fiscal_end': entry.get('fiscal_end')} for entry in revenue_history}

        # Create mapping of year to debt_to_equity for easy lookup
        debt_to_equity_by_year = {entry['year']: entry['debt_to_equity'] for entry in debt_to_equity_history}

        # Create mapping of year to EPS for easy lookup (for backward compatibility)
        eps_by_year = {entry['year']: entry['eps'] for entry in calculated_eps_history}

        # Track years that need D/E data
        years_needing_de = []

        # Store each year's data using Net Income
        for ni_entry in net_income_annual:
            year = ni_entry['year']
            net_income = ni_entry.get('net_income')
            fiscal_end = ni_entry.get('fiscal_end')
            revenue_data = revenue_by_year.get(year)
            debt_to_equity = debt_to_equity_by_year.get(year)
            eps = eps_by_year.get(year)

            if year and net_income and revenue_data:
                revenue = revenue_data['revenue']
                # Prefer revenue's fiscal_end if available, otherwise use NI's fiscal_end
                final_fiscal_end = revenue_data.get('fiscal_end') or fiscal_end
                self.db.save_earnings_history(symbol, year, float(eps) if eps else None, float(revenue), fiscal_end=final_fiscal_end, debt_to_equity=debt_to_equity, net_income=float(net_income))
                logger.debug(f"[{symbol}] Stored EDGAR Net Income for {year}: ${net_income:,.0f}, Revenue: ${revenue:,.0f}")

                # Track years missing D/E data
                if debt_to_equity is None:
                    years_needing_de.append(year)

        # If EDGAR didn't provide D/E data, try to get it from yfinance
        if years_needing_de:
            logger.info(f"[{symbol}] EDGAR missing D/E for {len(years_needing_de)} years. Fetching from yfinance balance sheet")
            self._backfill_debt_to_equity(symbol, years_needing_de)

    # todo: can this be collapsed with _store_edgar_earnings?
    def _store_edgar_quarterly_earnings(self, symbol: str, edgar_data: Dict[str, Any]):
        """Store quarterly earnings history from EDGAR data using Net Income"""
        # Use net_income_quarterly (raw quarterly Net Income from EDGAR)
        net_income_quarterly = edgar_data.get('net_income_quarterly', [])

        if not net_income_quarterly:
            logger.warning(f"[{symbol}] No quarterly Net Income data available from EDGAR")
            return

        quarters_stored = 0
        for entry in net_income_quarterly:
            year = entry['year']
            quarter = entry['quarter']
            net_income = entry.get('net_income')
            fiscal_end = entry.get('fiscal_end')

            if year and quarter and net_income:
                # Store with period like 'Q1', 'Q2', 'Q3', 'Q4'
                self.db.save_earnings_history(
                    symbol,
                    year,
                    None,  # No EPS for quarterly data
                    None,  # No revenue for quarterly data
                    fiscal_end=fiscal_end,
                    debt_to_equity=None,  # No D/E for quarterly data
                    period=quarter,
                    net_income=float(net_income)
                )
                quarters_stored += 1

        logger.info(f"[{symbol}] Stored {quarters_stored} quarters of EDGAR Net Income data")

    def _backfill_debt_to_equity(self, symbol: str, years: List[int]):
        """
        Backfill missing debt-to-equity data from yfinance balance sheets

        Args:
            symbol: Stock symbol
            years: List of years that need D/E data
        """
        try:
            stock = yf.Ticker(symbol)
            balance_sheet = stock.balance_sheet

            if balance_sheet is None or balance_sheet.empty:
                logger.warning(f"[{symbol}] No balance sheet data available from yfinance")
                return

            de_filled_count = 0
            for col in balance_sheet.columns:
                year = col.year if hasattr(col, 'year') else None
                if year and year in years:
                    debt_to_equity = self._calculate_debt_to_equity(balance_sheet, col)
                    if debt_to_equity is not None:
                        # Update the existing record with D/E data
                        conn = self.db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE earnings_history
                            SET debt_to_equity = ?
                            WHERE symbol = ? AND year = ? AND period = 'annual'
                        """, (debt_to_equity, symbol, year))
                        conn.commit()
                        conn.close()
                        de_filled_count += 1
                        logger.debug(f"[{symbol}] Backfilled D/E for {year}: {debt_to_equity:.2f}")

            if de_filled_count > 0:
                logger.info(f"[{symbol}] Successfully backfilled D/E for {de_filled_count}/{len(years)} years from yfinance")
            else:
                logger.warning(f"[{symbol}] Could not backfill any D/E data from yfinance")

        except Exception as e:
            logger.error(f"[{symbol}] Error backfilling D/E data: {type(e).__name__}: {e}")

    def _calculate_debt_to_equity(self, balance_sheet, col) -> Optional[float]:
        """
        Calculate debt-to-equity ratio from balance sheet data

        Args:
            balance_sheet: pandas DataFrame containing balance sheet data
            col: column/date to extract data from

        Returns:
            Debt-to-equity ratio or None if data unavailable
        """
        try:
            # Try to get Total Liabilities and Stockholder Equity
            liabilities = None
            equity = None

            if 'Total Liabilities Net Minority Interest' in balance_sheet.index:
                liabilities = balance_sheet.loc['Total Liabilities Net Minority Interest', col]
            elif 'Total Liab' in balance_sheet.index:
                liabilities = balance_sheet.loc['Total Liab', col]

            if 'Stockholders Equity' in balance_sheet.index:
                equity = balance_sheet.loc['Stockholders Equity', col]
            elif 'Total Stockholder Equity' in balance_sheet.index:
                equity = balance_sheet.loc['Total Stockholder Equity', col]

            # Calculate D/E ratio if both values are available and valid
            if pd.notna(liabilities) and pd.notna(equity) and equity != 0:
                return float(liabilities / equity)

            return None
        except Exception as e:
            logger.debug(f"Error calculating D/E ratio: {e}")
            return None

    def _fetch_and_store_earnings(self, symbol: str, stock):
        try:
            # Fetch annual data
            financials = stock.financials
            balance_sheet = stock.balance_sheet

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
                        debt_to_equity = self._calculate_debt_to_equity(balance_sheet, col)

                    if year and pd.notna(revenue) and pd.notna(eps):
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period='annual',
                                                     net_income=float(net_income) if pd.notna(net_income) else None)

            # Fetch quarterly data
            quarterly_financials = stock.quarterly_financials
            quarterly_balance_sheet = stock.quarterly_balance_sheet

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
                        debt_to_equity = self._calculate_debt_to_equity(quarterly_balance_sheet, col)

                    if year and quarter and pd.notna(revenue) and pd.notna(eps):
                        period = f'Q{quarter}'
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period=period,
                                                     net_income=float(net_income) if pd.notna(net_income) else None)

        except Exception as e:
            logger.error(f"[{symbol}] Error fetching earnings from yfinance: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def _fetch_quarterly_earnings(self, symbol: str, stock):
        """Fetch and store ONLY quarterly earnings data from yfinance"""
        try:
            # Fetch quarterly data only
            quarterly_financials = stock.quarterly_financials
            quarterly_balance_sheet = stock.quarterly_balance_sheet

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
                        debt_to_equity = self._calculate_debt_to_equity(quarterly_balance_sheet, col)

                    if year and quarter and pd.notna(revenue) and pd.notna(eps):
                        period = f'Q{quarter}'
                        self.db.save_earnings_history(symbol, year, float(eps), float(revenue),
                                                     debt_to_equity=debt_to_equity, period=period,
                                                     net_income=float(net_income) if pd.notna(net_income) else None)
            else:
                logger.warning(f"[{symbol}] No quarterly financial data available from yfinance")

        except Exception as e:
            logger.error(f"[{symbol}] Error fetching quarterly earnings from yfinance: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    def fetch_multiple_stocks(self, symbols: List[str], force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        results = {}
        for symbol in symbols:
            data = self.fetch_stock_data(symbol, force_refresh)
            if data:
                results[symbol] = data
        return results

    def get_nyse_nasdaq_symbols(self) -> List[str]:
        try:
            nyse_url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nyse/nyse_tickers.txt"
            nasdaq_url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nasdaq/nasdaq_tickers.txt"

            nyse_symbols = pd.read_csv(nyse_url, header=None)[0].tolist()
            nasdaq_symbols = pd.read_csv(nasdaq_url, header=None)[0].tolist()

            all_symbols = list(set(nyse_symbols + nasdaq_symbols))

            all_symbols = [s for s in all_symbols if isinstance(s, str)]

            return sorted(all_symbols)
        except Exception as e:
            print(f"Error fetching stock symbols: {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
