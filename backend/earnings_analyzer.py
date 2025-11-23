# ABOUTME: Analyzes 5-year earnings history to calculate growth rates and consistency
# ABOUTME: Provides earnings and revenue growth metrics for Peter Lynch criteria

from typing import Dict, Any, Optional, List
from database import Database
import math


class EarningsAnalyzer:
    def __init__(self, db: Database):
        self.db = db

    def calculate_earnings_growth(self, symbol: str) -> Optional[Dict[str, Any]]:
        history = self.db.get_earnings_history(symbol)

        if len(history) < 3:
            return None

        history_sorted = sorted(history, key=lambda x: x['year'])

        # Use Net Income instead of EPS for growth calculations
        net_income_values = [h.get('net_income') for h in history_sorted]
        revenue_values = [h['revenue'] for h in history_sorted]

        # Filter out entries without net_income data
        if not all(ni is not None for ni in net_income_values):
            return None

        if any(v <= 0 for v in net_income_values[:1]):
            return None

        start_net_income = net_income_values[0]
        end_net_income = net_income_values[-1]
        start_revenue = revenue_values[0]
        end_revenue = revenue_values[-1]
        years = len(history_sorted) - 1

        earnings_cagr = self.calculate_cagr(start_net_income, end_net_income, years)
        revenue_cagr = self.calculate_cagr(start_revenue, end_revenue, years)
        consistency_score = self.calculate_growth_consistency(net_income_values)

        return {
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'consistency_score': consistency_score
        }

    def calculate_cagr(self, start_value: float, end_value: float, years: int) -> Optional[float]:
        # Check for None values before comparison
        if start_value is None or end_value is None or years is None:
            return None
        if start_value <= 0 or end_value <= 0 or years <= 0:
            return None

        cagr = (math.pow(end_value / start_value, 1 / years) - 1) * 100
        return cagr

    def calculate_growth_consistency(self, values: List[float]) -> Optional[float]:
        if len(values) < 2:
            return None
        # Check if the first value is None or <= 0, as it's used as a denominator in growth rate calculation
        if values[0] is None or values[0] <= 0:
            return None

        growth_rates = []
        negative_year_penalty = 0
        has_negative_years = False
        
        for i in range(1, len(values)):
            if values[i] is not None and values[i-1] is not None and values[i-1] > 0:
                growth_rate = ((values[i] - values[i-1]) / values[i-1]) * 100
                growth_rates.append(growth_rate)
            
            # Track negative net income years
            if values[i] is not None and values[i] < 0:
                negative_year_penalty += 50  # Add 50 to std_dev for each negative year
                has_negative_years = True

        # If we have negative years but insufficient valid growth rates,
        # return a high penalty instead of None (which would default to neutral 50)
        if has_negative_years and len(growth_rates) < 3:
            return 200  # Very high std_dev = very low consistency score

        # Require at least 3 valid growth rate calculations for meaningful consistency
        if len(growth_rates) < 3:
            return None

        mean = sum(growth_rates) / len(growth_rates)
        variance = sum((x - mean) ** 2 for x in growth_rates) / len(growth_rates)
        std_dev = math.sqrt(variance)
        
        # Add penalty for negative years to the standard deviation
        return std_dev + negative_year_penalty
