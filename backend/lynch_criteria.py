# ABOUTME: Evaluates stocks against Peter Lynch investment criteria
# ABOUTME: Flags stocks as PASS, CLOSE, or FAIL based on PEG ratio, debt, growth, and ownership

from typing import Dict, Any, Optional
from database import Database
from earnings_analyzer import EarningsAnalyzer


class LynchCriteria:
    # PEG Ratio thresholds (lower is better)
    PEG_EXCELLENT = 1.0
    PEG_GOOD = 1.5
    PEG_FAIR = 2.0

    # Debt to Equity thresholds (lower is better)
    DEBT_EXCELLENT = 0.5
    DEBT_GOOD = 1.0
    DEBT_MODERATE = 2.0

    # Institutional Ownership thresholds (sweet spot in middle)
    INST_OWN_TOO_LOW = 0.20
    INST_OWN_IDEAL_MIN = 0.20
    INST_OWN_IDEAL_MAX = 0.60
    INST_OWN_TOO_HIGH = 0.60

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
            peg_score = 0.0
        else:
            peg_status = self.evaluate_peg(peg_ratio)
            peg_score = self.calculate_peg_score(peg_ratio)

        debt_status = self.evaluate_debt(debt_to_equity)
        debt_score = self.calculate_debt_score(debt_to_equity)

        inst_ownership_status = self.evaluate_institutional_ownership(institutional_ownership)
        inst_ownership_score = self.calculate_institutional_ownership_score(institutional_ownership)

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
            'country': metrics.get('country'),
            'market_cap': metrics.get('market_cap'),
            'sector': metrics.get('sector'),
            'ipo_year': metrics.get('ipo_year'),
            'price': metrics.get('price'),
            'pe_ratio': pe_ratio,
            'peg_ratio': peg_ratio,
            'debt_to_equity': debt_to_equity,
            'institutional_ownership': institutional_ownership,
            'dividend_yield': metrics.get('dividend_yield'),
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'consistency_score': consistency_score,
            'peg_status': peg_status,
            'peg_score': peg_score,
            'debt_status': debt_status,
            'debt_score': debt_score,
            'institutional_ownership_status': inst_ownership_status,
            'institutional_ownership_score': inst_ownership_score,
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

    def evaluate_peg(self, value: float) -> str:
        """Evaluate PEG ratio: lower is better"""
        if value is None:
            return "FAIL"
        if value <= self.PEG_EXCELLENT:
            return "PASS"
        elif value <= self.PEG_GOOD:
            return "CLOSE"
        else:
            return "FAIL"

    def calculate_peg_score(self, value: float) -> float:
        """
        Calculate PEG score (0-100).
        Excellent (0-1.0): 100
        Good (1.0-1.5): 75-100
        Fair (1.5-2.0): 25-75
        Poor (2.0+): 0-25
        """
        if value is None:
            return 0.0
        if value <= self.PEG_EXCELLENT:
            return 100.0
        elif value <= self.PEG_GOOD:
            # 75-100 range
            range_size = self.PEG_GOOD - self.PEG_EXCELLENT
            position = (self.PEG_GOOD - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= self.PEG_FAIR:
            # 25-75 range
            range_size = self.PEG_FAIR - self.PEG_GOOD
            position = (self.PEG_FAIR - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 4.0
            max_poor = 4.0
            if value >= max_poor:
                return 0.0
            range_size = max_poor - self.PEG_FAIR
            position = (max_poor - value) / range_size
            return 25.0 * position

    def evaluate_debt(self, value: float) -> str:
        """Evaluate Debt to Equity: lower is better"""
        if value is None:
            return "FAIL"
        if value <= self.DEBT_EXCELLENT:
            return "PASS"
        elif value <= self.DEBT_GOOD:
            return "CLOSE"
        else:
            return "FAIL"

    def calculate_debt_score(self, value: float) -> float:
        """
        Calculate Debt score (0-100).
        Excellent (0-0.5): 100
        Good (0.5-1.0): 75-100
        Moderate (1.0-2.0): 25-75
        High (2.0+): 0-25
        """
        if value is None:
            return 0.0
        if value <= self.DEBT_EXCELLENT:
            return 100.0
        elif value <= self.DEBT_GOOD:
            # 75-100 range
            range_size = self.DEBT_GOOD - self.DEBT_EXCELLENT
            position = (self.DEBT_GOOD - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= self.DEBT_MODERATE:
            # 25-75 range
            range_size = self.DEBT_MODERATE - self.DEBT_GOOD
            position = (self.DEBT_MODERATE - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 5.0
            max_high = 5.0
            if value >= max_high:
                return 0.0
            range_size = max_high - self.DEBT_MODERATE
            position = (max_high - value) / range_size
            return 25.0 * position

    def evaluate_institutional_ownership(self, value: float) -> str:
        """Evaluate Institutional Ownership: sweet spot in middle (20%-60%)"""
        if value is None:
            return "FAIL"
        if self.INST_OWN_IDEAL_MIN <= value <= self.INST_OWN_IDEAL_MAX:
            return "PASS"
        elif value < self.INST_OWN_TOO_LOW or value > self.INST_OWN_TOO_HIGH:
            return "FAIL"
        else:
            return "CLOSE"

    def calculate_institutional_ownership_score(self, value: float) -> float:
        """
        Calculate Institutional Ownership score (0-100).
        Sweet spot (20%-60%): 100 at center (40%), tapering to 75 at edges
        Too low (0-20%): 0-75
        Too high (60%-100%): 75-0
        """
        if value is None:
            return 0.0

        # Ideal range: 20%-60%, peak at 40%
        ideal_center = 0.40

        if self.INST_OWN_IDEAL_MIN <= value <= self.INST_OWN_IDEAL_MAX:
            # In ideal range: score 75-100
            # Calculate distance from center
            distance_from_center = abs(value - ideal_center)
            max_distance = ideal_center - self.INST_OWN_IDEAL_MIN  # 0.20
            position = 1.0 - (distance_from_center / max_distance)
            return 75.0 + (25.0 * position)
        elif value < self.INST_OWN_IDEAL_MIN:
            # Too low: 0-75
            if value <= 0:
                return 0.0
            position = value / self.INST_OWN_IDEAL_MIN
            return 75.0 * position
        else:
            # Too high: 75-0
            if value >= 1.0:
                return 0.0
            range_size = 1.0 - self.INST_OWN_IDEAL_MAX
            position = (1.0 - value) / range_size
            return 75.0 * position
