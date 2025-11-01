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

        eps_values = [h['eps'] for h in history_sorted]
        revenue_values = [h['revenue'] for h in history_sorted]

        if any(v <= 0 for v in eps_values[:1]):
            return None

        start_eps = eps_values[0]
        end_eps = eps_values[-1]
        start_revenue = revenue_values[0]
        end_revenue = revenue_values[-1]
        years = len(history_sorted) - 1

        earnings_cagr = self.calculate_cagr(start_eps, end_eps, years)
        revenue_cagr = self.calculate_cagr(start_revenue, end_revenue, years)
        consistency_score = self.calculate_growth_consistency(eps_values)

        return {
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'consistency_score': consistency_score
        }

    def calculate_cagr(self, start_value: float, end_value: float, years: int) -> Optional[float]:
        if start_value <= 0 or years <= 0:
            return None

        cagr = (math.pow(end_value / start_value, 1 / years) - 1) * 100
        return cagr

    def calculate_growth_consistency(self, values: List[float]) -> Optional[float]:
        if len(values) < 2:
            return None

        growth_rates = []
        for i in range(1, len(values)):
            if values[i-1] > 0:
                growth_rate = ((values[i] - values[i-1]) / values[i-1]) * 100
                growth_rates.append(growth_rate)

        if not growth_rates:
            return None

        mean = sum(growth_rates) / len(growth_rates)
        variance = sum((x - mean) ** 2 for x in growth_rates) / len(growth_rates)
        std_dev = math.sqrt(variance)

        return std_dev
