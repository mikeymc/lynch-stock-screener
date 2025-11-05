# ABOUTME: Evaluates stocks against Peter Lynch investment criteria
# ABOUTME: Flags stocks as PASS, CLOSE, or FAIL based on PEG ratio, debt, growth, and ownership

from typing import Dict, Any, Optional
from database import Database
from earnings_analyzer import EarningsAnalyzer


class LynchCriteria:
    PEG_IDEAL = 1.0
    PEG_CLOSE = 1.15
    DEBT_TO_EQUITY_IDEAL = 0.5
    DEBT_TO_EQUITY_CLOSE = 0.6
    INSTITUTIONAL_OWNERSHIP_IDEAL = 0.5
    INSTITUTIONAL_OWNERSHIP_CLOSE = 0.55

    def __init__(self, db: Database, analyzer: EarningsAnalyzer):
        self.db = db
        self.analyzer = analyzer

    def evaluate_stock(self, symbol: str) -> Optional[Dict[str, Any]]:
        metrics = self.db.get_stock_metrics(symbol)
        if not metrics:
            return None

        growth_data = self.analyzer.calculate_earnings_growth(symbol)

        # Extract growth data or None if unavailable
        earnings_cagr = growth_data['earnings_cagr'] if growth_data else None
        revenue_cagr = growth_data['revenue_cagr'] if growth_data else None
        consistency_score = growth_data['consistency_score'] if growth_data else None

        pe_ratio = metrics.get('pe_ratio')

        # Calculate PEG ratio only if both P/E and earnings growth are available
        peg_ratio = self.calculate_peg_ratio(pe_ratio, earnings_cagr) if pe_ratio and earnings_cagr else None

        debt_to_equity = metrics.get('debt_to_equity', 0)
        institutional_ownership = metrics.get('institutional_ownership', 0)

        if peg_ratio is None:
            peg_status = "FAIL"
        else:
            peg_status = self.evaluate_criterion(peg_ratio, self.PEG_IDEAL, self.PEG_CLOSE, lower_is_better=True)
        debt_status = self.evaluate_criterion(debt_to_equity, self.DEBT_TO_EQUITY_IDEAL, self.DEBT_TO_EQUITY_CLOSE, lower_is_better=True)
        inst_ownership_status = self.evaluate_criterion(institutional_ownership, self.INSTITUTIONAL_OWNERSHIP_IDEAL, self.INSTITUTIONAL_OWNERSHIP_CLOSE, lower_is_better=True)

        statuses = [peg_status, debt_status, inst_ownership_status]

        if all(s == "PASS" for s in statuses):
            overall_status = "PASS"
        elif any(s == "FAIL" for s in statuses):
            overall_status = "FAIL"
        else:
            overall_status = "CLOSE"

        return {
            'symbol': symbol,
            'company_name': metrics.get('company_name'),
            'price': metrics.get('price'),
            'pe_ratio': pe_ratio,
            'peg_ratio': peg_ratio,
            'debt_to_equity': debt_to_equity,
            'institutional_ownership': institutional_ownership,
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'consistency_score': consistency_score,
            'peg_status': peg_status,
            'debt_status': debt_status,
            'institutional_ownership_status': inst_ownership_status,
            'overall_status': overall_status
        }

    def calculate_peg_ratio(self, pe_ratio: float, earnings_growth: float) -> Optional[float]:
        if pe_ratio is None or earnings_growth is None:
            return None
        if isinstance(pe_ratio, str) or isinstance(earnings_growth, str):
            return None
        if earnings_growth <= 0:
            return None
        return pe_ratio / earnings_growth

    def evaluate_criterion(self, value: float, ideal_threshold: float, close_threshold: float, lower_is_better: bool = True) -> str:
        if value is None:
            return "FAIL"

        if lower_is_better:
            if value <= ideal_threshold:
                return "PASS"
            elif value <= close_threshold:
                return "CLOSE"
            else:
                return "FAIL"
        else:
            if value >= ideal_threshold:
                return "PASS"
            elif value >= close_threshold:
                return "CLOSE"
            else:
                return "FAIL"
