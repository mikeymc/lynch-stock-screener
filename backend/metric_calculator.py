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

    def calculate_debt_to_earnings(self, symbol: str, total_debt: float = None) -> Dict[str, Any]:
        """Calculate years to pay off debt with current earnings.

        Debt-to-Earnings = Total Debt / Annual Net Income

        Buffett prefers companies that can pay off debt in 3-4 years.

        Args:
            symbol: Stock ticker
            total_debt: Optional pre-fetched total_debt to avoid DB lookup

        Returns:
            Dict with debt_to_earnings_years and related metrics
        """
        result = {
            'debt_to_earnings_years': None,
            'total_debt': None,
            'annual_net_income': None,
        }

        # Use provided total_debt if available, otherwise fetch from DB
        if total_debt is None:
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

        if total_debt is not None and net_income and net_income > 0:
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

    def calculate_gross_margin(self, symbol: str, years: int = 5) -> Dict[str, Any]:
        """Calculate gross margin metrics from yfinance income statement.

        Gross Margin = Gross Profit / Total Revenue

        Stable or growing gross margins suggest pricing power / moat.

        Args:
            symbol: Stock ticker
            years: Number of years to analyze

        Returns:
            Dict with current, average, trend, and history
        """
        result = {
            'current': None,
            'average': None,
            'trend': None,  # 'stable', 'improving', 'declining'
            'history': [],
        }

        try:
            import yfinance as yf
            import pandas as pd
            import numpy as np

            ticker = yf.Ticker(symbol)
            income_stmt = ticker.income_stmt

            if income_stmt is None or income_stmt.empty:
                return result

            # Look for gross profit and revenue
            gross_profit_key = None
            revenue_key = None

            for key in ['Gross Profit', 'GrossProfit']:
                if key in income_stmt.index:
                    gross_profit_key = key
                    break

            for key in ['Total Revenue', 'TotalRevenue', 'Revenue']:
                if key in income_stmt.index:
                    revenue_key = key
                    break

            if not gross_profit_key or not revenue_key:
                logger.debug(f"{symbol}: Missing gross profit or revenue in income statement")
                return result

            margins = []
            for col in income_stmt.columns[:years]:  # Most recent N years
                year = col.year if hasattr(col, 'year') else pd.Timestamp(col).year
                gross_profit = income_stmt.loc[gross_profit_key, col]
                revenue = income_stmt.loc[revenue_key, col]

                if pd.notna(gross_profit) and pd.notna(revenue) and revenue != 0:
                    margin = (gross_profit / revenue) * 100  # as percentage
                    margins.append({'year': year, 'margin': round(margin, 2)})

            if not margins:
                return result

            # Sort by year descending (most recent first)
            margins.sort(key=lambda x: x['year'], reverse=True)
            result['history'] = margins

            # Current (most recent year)
            result['current'] = margins[0]['margin'] if margins else None

            # Average
            margin_values = [m['margin'] for m in margins]
            result['average'] = round(sum(margin_values) / len(margin_values), 2)

            # Trend analysis
            if len(margin_values) >= 3:
                std_dev = np.std(margin_values)
                first_half = margin_values[len(margin_values)//2:]  # Older years
                second_half = margin_values[:len(margin_values)//2]  # Recent years

                avg_first = sum(first_half) / len(first_half) if first_half else 0
                avg_second = sum(second_half) / len(second_half) if second_half else 0

                if std_dev < 2:
                    result['trend'] = 'stable'
                elif avg_second > avg_first + 1:
                    result['trend'] = 'improving'
                elif avg_second < avg_first - 1:
                    result['trend'] = 'declining'
                else:
                    result['trend'] = 'stable'

            return result

        except Exception as e:
            logger.warning(f"Failed to calculate gross margin for {symbol}: {e}")
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
        gross_margin_data = self.calculate_gross_margin(symbol)

        return {
            'roe': {
                'current': roe_data['current_roe'],
                'avg_5yr': roe_data['avg_roe_5yr'],
                'avg_10yr': roe_data['avg_roe_10yr'],
            },
            'owner_earnings': owner_earnings_data['owner_earnings'],
            'debt_to_earnings_years': debt_data['debt_to_earnings_years'],
            'earnings_consistency': consistency_data['earnings_consistency'],
            'gross_margin': {
                'current': gross_margin_data['current'],
                'average': gross_margin_data['average'],
                'trend': gross_margin_data['trend'],
            },
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

    def calculate_pe_52_week_range(self, symbol: str, stock: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate the 52-week P/E range (min, max, current position).
        Uses Quarterly TTM EPS (Rolling 4-Quarter Sum) for accuracy.
        
        Args:
            symbol: Stock symbol
            stock: Dictionary containing current stock metrics (price, pe_ratio, etc.)
        """
        from datetime import datetime, timedelta
        
        result = {
            'pe_52_week_min': None,
            'pe_52_week_max': None,
            'pe_52_week_position': None
        }
        
        # Defensive check for stock data
        if not isinstance(stock, dict):
            logger.warning(f" [MetricCalculator] Invalid stock data for {symbol}: expected dict, got {type(stock)}")
            return result
            
        try:
            weekly_prices = self.db.get_weekly_prices(symbol)
            if not isinstance(weekly_prices, dict):
                return result
            
            shares_outstanding = stock.get('shares_outstanding')
            
            # If standard shares calculation fails, try stock_metrics if available
            if not shares_outstanding and stock.get('market_cap') and stock.get('price'):
                shares_outstanding = stock.get('market_cap') / stock.get('price')

            if not weekly_prices or not weekly_prices.get('dates') or not weekly_prices.get('prices'):
                return result
            
            if not shares_outstanding:
                return result
                
            # Get earnings history
            earnings_history = self.db.get_earnings_history(symbol, period_type='quarterly')
            if not earnings_history or not isinstance(earnings_history, list):
                return result
            
            # Filter for quarterly net_income
            quarterly_data = []
            for e in earnings_history:
                if isinstance(e, dict) and e.get('period') in ['Q1', 'Q2', 'Q3', 'Q4'] and e.get('net_income') is not None:
                    quarterly_data.append(e)
            
            # Sort by fiscal_end
            quarterly_data.sort(key=lambda x: x.get('fiscal_end') or '')
            
            if len(quarterly_data) < 4:
                return result

            # Calculate cutoff date for 52 weeks ago
            cutoff_date = datetime.now() - timedelta(weeks=52)
            cutoff_str = cutoff_date.strftime('%Y-%m-%d')
            
            pe_values = []
            
            for i, date_str in enumerate(weekly_prices['dates']):
                # Only include last 52 weeks
                ds = str(date_str)
                if ds < cutoff_str:
                    continue
                
                price = weekly_prices['prices'][i]
                if not price or price <= 0:
                    continue
                    
                # Find valid quarters (fiscal_end <= current_week)
                # Ensure date comparison is string-safe
                valid_quarters = []
                for q in quarterly_data:
                    # Defensive check: ensure q is a dict before accessing
                    if isinstance(q, dict) and q.get('fiscal_end') and str(q['fiscal_end']) <= ds:
                        valid_quarters.append(q)
                
                if len(valid_quarters) >= 4:
                    last_4 = valid_quarters[-4:]
                    ttm_net_income = sum(q['net_income'] for q in last_4)
                    
                    if ttm_net_income > 0:
                        # TTM EPS = TTM Net Income / Current Shares
                        # Usage of Current Shares is valid because Prices are Split-Adjusted (from yfinance)
                        ttm_eps = ttm_net_income / shares_outstanding
                        
                        if ttm_eps > 0:
                            pe = price / ttm_eps
                            if pe < 1000: # Filter outliers
                                pe_values.append(pe)

            if not pe_values:
                return result
                
            pe_min = min(pe_values)
            pe_max = max(pe_values)
            
            # Current Position Logic
            # Compare LIVE P/E against the TTM Range we just built
            current_pe = stock.get('pe_ratio')
            
            position = 50.0 
            
            if pe_max > pe_min and current_pe is not None:
                if current_pe < pe_min:
                    position = 0.0
                elif current_pe > pe_max:
                    position = 100.0
                else:
                    position = ((current_pe - pe_min) / (pe_max - pe_min)) * 100
            
            result['pe_52_week_min'] = round(pe_min, 2)
            result['pe_52_week_max'] = round(pe_max, 2)
            result['pe_52_week_position'] = round(position, 1)
            
        except Exception as e:
            # Catch-all to prevent crash on unexpected data
            logger.error(f"Error calculating P/E range for {symbol}: {e}")
            
        return result
