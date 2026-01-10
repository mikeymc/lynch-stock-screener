# ABOUTME: Computes derived financial metrics for different investment characters
# ABOUTME: Calculates ROE, owner earnings, debt-to-earnings, etc. on the fly

import logging
from typing import Dict, Any, Optional, List
from database import Database

logger = logging.getLogger(__name__)


class MetricCalculator:
    """Calculates derived metrics for stock analysis.

    Some metrics (like PEG, P/E) are stored directly in the database.
    Others (like ROE, owner earnings) need to be computed from raw financial data.
    This class handles the computation, fetching additional data from yfinance if needed.
    """

    def __init__(self, db: Database):
        self.db = db

    def calculate_roe(self, symbol: str, years: int = 5) -> Dict[str, Any]:
        """Calculate Return on Equity metrics.

        ROE = Net Income / Shareholders Equity

        Args:
            symbol: Stock ticker
            years: Number of years for average (default 5)

        Returns:
            Dict with current_roe, avg_roe, and roe_history
        """
        result = {
            'current_roe': None,
            'avg_roe_5yr': None,
            'avg_roe_10yr': None,
            'roe_history': [],
        }

        # Get earnings history (has net_income)
        earnings_history = self.db.get_earnings_history(symbol, 'annual')
        if not earnings_history:
            return result

        # Get equity data from yfinance
        equity_by_year = self._fetch_equity_history(symbol)
        if not equity_by_year:
            return result

        # Calculate ROE for each year we have both net income and equity
        roe_values = []
        for entry in earnings_history:
            year = entry.get('year')
            net_income = entry.get('net_income')
            equity = equity_by_year.get(year)

            if net_income and equity and equity > 0:
                roe = (net_income / equity) * 100  # as percentage
                roe_values.append({'year': year, 'roe': round(roe, 2)})

        if not roe_values:
            return result

        # Sort by year descending
        roe_values.sort(key=lambda x: x['year'], reverse=True)
        result['roe_history'] = roe_values

        # Current ROE (most recent year)
        result['current_roe'] = roe_values[0]['roe'] if roe_values else None

        # 5-year average
        recent_5 = [r['roe'] for r in roe_values[:5]]
        if recent_5:
            result['avg_roe_5yr'] = round(sum(recent_5) / len(recent_5), 2)

        # 10-year average
        recent_10 = [r['roe'] for r in roe_values[:10]]
        if len(recent_10) >= 5:  # Only compute if we have at least 5 years
            result['avg_roe_10yr'] = round(sum(recent_10) / len(recent_10), 2)

        return result

    def calculate_owner_earnings(self, symbol: str) -> Dict[str, Any]:
        """Calculate Owner Earnings (Buffett's preferred metric).

        Owner Earnings = Net Income + Depreciation - Maintenance CapEx

        Since we can't separate maintenance vs growth capex, we use:
        Owner Earnings = Operating Cash Flow - Maintenance CapEx (estimated as 70% of total capex)

        Args:
            symbol: Stock ticker

        Returns:
            Dict with owner_earnings and related metrics
        """
        result = {
            'owner_earnings': None,
            'owner_earnings_per_share': None,
            'fcf_to_owner_earnings_ratio': None,
        }

        # Get most recent annual earnings data
        earnings_history = self.db.get_earnings_history(symbol, 'annual')
        if not earnings_history:
            return result

        # Use most recent year
        latest = earnings_history[0]
        net_income = latest.get('net_income')
        operating_cf = latest.get('operating_cash_flow')
        capex = latest.get('capital_expenditures')
        fcf = latest.get('free_cash_flow')

        if operating_cf and capex:
            # Estimate maintenance capex as 70% of total capex
            # (This is a rough heuristic - growth companies spend more on growth capex)
            maintenance_capex = abs(capex) * 0.7
            owner_earnings = operating_cf - maintenance_capex
            result['owner_earnings'] = round(owner_earnings / 1_000_000, 2)  # in millions

            if fcf:
                result['fcf_to_owner_earnings_ratio'] = round(fcf / owner_earnings, 2) if owner_earnings else None

        return result

    def calculate_debt_to_earnings(self, symbol: str) -> Dict[str, Any]:
        """Calculate years to pay off debt with current earnings.

        Debt-to-Earnings = Total Debt / Annual Net Income

        Buffett prefers companies that can pay off debt in 3-4 years.

        Args:
            symbol: Stock ticker

        Returns:
            Dict with debt_to_earnings_years and related metrics
        """
        result = {
            'debt_to_earnings_years': None,
            'total_debt': None,
            'annual_net_income': None,
        }

        # Get total debt from stock_metrics
        metrics = self.db.get_stock_metrics(symbol)
        if not metrics:
            return result

        total_debt = metrics.get('total_debt')
        result['total_debt'] = total_debt

        # Get net income from earnings history
        earnings_history = self.db.get_earnings_history(symbol, 'annual')
        if not earnings_history:
            return result

        # Use most recent year's net income
        latest = earnings_history[0]
        net_income = latest.get('net_income')
        result['annual_net_income'] = net_income

        if total_debt and net_income and net_income > 0:
            years_to_payoff = total_debt / net_income
            result['debt_to_earnings_years'] = round(years_to_payoff, 2)

        return result

    def calculate_earnings_consistency(self, symbol: str) -> Dict[str, Any]:
        """Calculate earnings consistency score.

        This is already computed in the earnings analyzer, but we wrap it here
        for consistent interface.

        Returns:
            Dict with consistency_score (0-100)
        """
        result = {
            'earnings_consistency': None,
            'revenue_consistency': None,
        }

        # Get from screening results if available
        screening_result = self.db.get_screening_result_for_symbol(symbol)
        if screening_result:
            result['earnings_consistency'] = screening_result.get('consistency_score')

        return result

    def calculate_gross_margin_stability(self, symbol: str, years: int = 5) -> Dict[str, Any]:
        """Calculate gross margin stability (moat indicator).

        Stable or growing gross margins suggest pricing power / moat.

        Returns:
            Dict with current_gross_margin, avg_gross_margin, trend
        """
        result = {
            'current_gross_margin': None,
            'avg_gross_margin': None,
            'gross_margin_trend': None,  # 'stable', 'improving', 'declining'
        }

        # This would require gross profit data which we may not have
        # For now, return empty - can enhance later
        return result

    def get_buffett_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get all Buffett-relevant metrics for a stock.

        Convenience method that calculates all metrics Buffett cares about.

        Returns:
            Dict with all computed Buffett metrics
        """
        roe_data = self.calculate_roe(symbol)
        owner_earnings_data = self.calculate_owner_earnings(symbol)
        debt_data = self.calculate_debt_to_earnings(symbol)
        consistency_data = self.calculate_earnings_consistency(symbol)

        return {
            'roe': {
                'current': roe_data['current_roe'],
                'avg_5yr': roe_data['avg_roe_5yr'],
                'avg_10yr': roe_data['avg_roe_10yr'],
            },
            'owner_earnings': owner_earnings_data['owner_earnings'],
            'debt_to_earnings_years': debt_data['debt_to_earnings_years'],
            'earnings_consistency': consistency_data['earnings_consistency'],
        }

    def _fetch_equity_history(self, symbol: str) -> Dict[int, float]:
        """Fetch shareholders equity by year from yfinance.

        Returns:
            Dict mapping year to equity value
        """
        try:
            import yfinance as yf
            import pandas as pd

            ticker = yf.Ticker(symbol)
            balance_sheet = ticker.balance_sheet

            if balance_sheet is None or balance_sheet.empty:
                return {}

            equity_by_year = {}

            # Look for equity in balance sheet
            equity_keys = [
                'Stockholders Equity',
                'Total Stockholders Equity',
                'Common Stock Equity',
                'Total Equity Gross Minority Interest',
            ]

            for col in balance_sheet.columns:
                year = col.year if hasattr(col, 'year') else pd.Timestamp(col).year

                for key in equity_keys:
                    if key in balance_sheet.index:
                        equity = balance_sheet.loc[key, col]
                        if pd.notna(equity) and equity != 0:
                            equity_by_year[year] = float(equity)
                            break

            return equity_by_year

        except Exception as e:
            logger.warning(f"Failed to fetch equity history for {symbol}: {e}")
            return {}
