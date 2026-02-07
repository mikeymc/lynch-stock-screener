# ABOUTME: Individual metric scoring methods for Lynch investment criteria.
# ABOUTME: Provides PEG, debt, ownership, and growth scoring as a mixin class.

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ScoringMixin:

    def calculate_peg_ratio(self, pe_ratio: float, earnings_growth: float) -> Optional[float]:
        if pe_ratio is None or earnings_growth is None:
            return None
        if isinstance(pe_ratio, str) or isinstance(earnings_growth, str):
            return None
        if earnings_growth <= 0:
            return None  # Can't calculate meaningful PEG for zero or negative growth
        return pe_ratio / earnings_growth

    def evaluate_peg(self, value: float) -> str:
        """Evaluate PEG ratio: lower is better"""
        if value is None:
            return "FAIL"

        # Safety: use defaults if loaded from non-Lynch character config
        peg_excellent = self.peg_excellent if self.peg_excellent is not None else 1.0
        peg_good = self.peg_good if self.peg_good is not None else 1.5

        try:
            if value <= peg_excellent:
                return "PASS"
            elif value <= peg_good:
                return "CLOSE"
            else:
                return "FAIL"
        except TypeError as e:
            logger.error(f"TypeError in evaluate_peg: value={value} ({type(value)}), excellent={peg_excellent} ({type(peg_excellent)}), good={peg_good} ({type(peg_good)})")
            raise e

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

        # Safety defaults
        peg_excellent = self.peg_excellent if self.peg_excellent is not None else 1.0
        peg_good = self.peg_good if self.peg_good is not None else 1.5
        peg_fair = self.peg_fair if self.peg_fair is not None else 2.0

        if value <= peg_excellent:
            return 100.0
        elif value <= peg_good:
            # 75-100 range
            range_size = peg_good - peg_excellent
            position = (peg_good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= peg_fair:
            # 25-75 range
            range_size = peg_fair - peg_good
            position = (peg_fair - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 4.0
            max_poor = 4.0
            if value >= max_poor:
                return 0.0
            range_size = max_poor - peg_fair
            position = (max_poor - value) / range_size
            return 25.0 * position

    def evaluate_debt(self, value: float) -> str:
        """Evaluate debt-to-equity: lower is better"""
        if value is None:
            return "PASS"  # Lynch liked no debt

        # Safety defaults
        debt_excellent = self.debt_excellent if self.debt_excellent is not None else 0.5
        debt_good = self.debt_good if self.debt_good is not None else 1.0

        try:
            if value <= debt_excellent:
                return "PASS"
            elif value <= debt_good:
                return "CLOSE"
            else:
                return "FAIL"
        except TypeError as e:
            logger.error(f"TypeError in evaluate_debt: value={value} ({type(value)}), excellent={debt_excellent}, good={debt_good}")
            raise e

    def calculate_debt_score(self, value: float) -> float:
        """
        Calculate debt score (0-100).
        Excellent (0-0.5): 100
        Good (0.5-1.0): 75-100
        Moderate (1.0-2.0): 25-75
        High (2.0+): 0-25
        """
        if value is None:
            return 100.0  # No debt is great

        # Safety defaults
        debt_excellent = self.debt_excellent if self.debt_excellent is not None else 0.5
        debt_good = self.debt_good if self.debt_good is not None else 1.0
        debt_moderate = self.debt_moderate if self.debt_moderate is not None else 2.0

        if value <= debt_excellent:
            return 100.0
        elif value <= debt_good:
            # 75-100 range
            range_size = debt_good - debt_excellent
            position = (debt_good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= debt_moderate:
            # 25-75 range
            range_size = debt_moderate - debt_good
            position = (debt_moderate - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 5.0
            max_high = 5.0
            if value >= max_high:
                return 0.0
            range_size = max_high - debt_moderate
            position = (max_high - value) / range_size
            return 25.0 * position

    def evaluate_institutional_ownership(self, value: float) -> str:
        """Evaluate institutional ownership: sweet spot is around 40%"""
        if value is None:
            return "PASS"

        # Safety defaults
        inst_own_min = self.inst_own_min if self.inst_own_min is not None else 0.20
        inst_own_max = self.inst_own_max if self.inst_own_max is not None else 0.60

        try:
            if inst_own_min <= value <= inst_own_max:
                return "PASS"
            elif value < inst_own_min:
                return "CLOSE"
            else:
                return "FAIL"
        except TypeError as e:
            logger.error(f"TypeError in evaluate_institutional_ownership: value={value}, min={inst_own_min}, max={inst_own_max}")
            raise e

    def calculate_institutional_ownership_score(self, value: float) -> float:
        """
        Calculate institutional ownership score (0-100).
        Sweet spot (20%-60%): 100
        Under-owned (< 20%): 50-100
        Over-owned (> 60%): 0-50
        """
        if value is None:
            return 75.0  # Neutral

        # Safety defaults
        inst_own_min = self.inst_own_min if self.inst_own_min is not None else 0.20
        inst_own_max = self.inst_own_max if self.inst_own_max is not None else 0.60

        if inst_own_min <= value <= inst_own_max:
            return 100.0
        elif value < inst_own_min:
            # Under-owned is okay (50-100)
            return 50.0 + (value / inst_own_min) * 50.0 if inst_own_min > 0 else 100.0
        else:
            # Over-owned is bad (0-50)
            # Dips to 0 at 100% ownership
            range_size = 1.0 - inst_own_max
            if range_size > 0:
                position = (1.0 - value) / range_size
                return max(0.0, 50.0 * position)
            return 0.0

    def calculate_revenue_growth_score(self, value: float) -> float:
        """
        Calculate Revenue Growth score (0-100).
        Excellent (15%+): 100
        Good (10-15%): 75-100
        Fair (5-10%): 25-75
        Poor (<5%): 0-25
        Negative growth: 0
        """
        if value is None:
            return 50.0  # Default neutral score if no data

        if value < 0:
            return 0.0  # Negative growth = 0 score

        # Safety defaults
        rev_excellent = self.revenue_growth_excellent if self.revenue_growth_excellent is not None else 15.0
        rev_good = self.revenue_growth_good if self.revenue_growth_good is not None else 10.0
        rev_fair = self.revenue_growth_fair if self.revenue_growth_fair is not None else 5.0

        if value >= rev_excellent:
            return 100.0
        elif value >= rev_good:
            # 75-100 range
            range_size = rev_excellent - rev_good
            position = (value - rev_good) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value >= rev_fair:
            # 25-75 range
            range_size = rev_good - rev_fair
            position = (value - rev_fair) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range
            if value <= 0:
                return 0.0
            position = value / rev_fair if rev_fair > 0 else 0.0
            return 25.0 * position

    def calculate_income_growth_score(self, value: float) -> float:
        """
        Calculate Income/Earnings Growth score (0-100).
        Excellent (15%+): 100
        Good (10-15%): 75-100
        Fair (5-10%): 25-75
        Poor (<5%): 0-25
        Negative growth: 0
        """
        if value is None:
            return 50.0  # Default neutral score if no data

        if value < 0:
            return 0.0  # Negative growth = 0 score

        # Safety defaults
        inc_excellent = self.income_growth_excellent if self.income_growth_excellent is not None else 15.0
        inc_good = self.income_growth_good if self.income_growth_good is not None else 10.0
        inc_fair = self.income_growth_fair if self.income_growth_fair is not None else 5.0

        if value >= inc_excellent:
            return 100.0
        elif value >= inc_good:
            # 75-100 range
            range_size = inc_excellent - inc_good
            position = (value - inc_good) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value >= inc_fair:
            # 25-75 range
            range_size = inc_good - inc_fair
            position = (value - inc_fair) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range
            if value <= 0:
                return 0.0
            position = value / inc_fair if inc_fair > 0 else 0.0
            return 25.0 * position

    # ========== Threshold-aware scoring methods (for optimizer overrides) ==========

    def _calculate_peg_score_with_thresholds(self, value: float, excellent: float, good: float, fair: float) -> float:
        """Calculate PEG score using custom thresholds (for optimizer overrides)"""
        if value is None:
            return 0.0

        # Safety defaults
        excellent = excellent if excellent is not None else 1.0
        good = good if good is not None else 1.5
        fair = fair if fair is not None else 2.0

        if value <= excellent:
            return 100.0
        elif value <= good:
            range_size = good - excellent
            position = (good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= fair:
            range_size = fair - good
            position = (fair - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            max_poor = 4.0
            if value >= max_poor:
                return 0.0
            range_size = max_poor - fair
            position = (max_poor - value) / range_size if range_size > 0 else 1.0
            return 25.0 * position

    def _calculate_debt_score_with_thresholds(self, value: float, excellent: float, good: float, moderate: float) -> float:
        """Calculate debt score using custom thresholds (for optimizer overrides)"""
        if value is None:
            return 100.0

        # Safety defaults
        excellent = excellent if excellent is not None else 0.5
        good = good if good is not None else 1.0
        moderate = moderate if moderate is not None else 2.0

        if value <= excellent:
            return 100.0
        elif value <= good:
            range_size = good - excellent
            position = (good - value) / range_size if range_size > 0 else 1.0
            return 75.0 + (25.0 * position)
        elif value <= moderate:
            range_size = moderate - good
            position = (moderate - value) / range_size if range_size > 0 else 1.0
            return 25.0 + (50.0 * position)
        else:
            max_high = 5.0
            if value >= max_high:
                return 0.0
            range_size = max_high - moderate
            position = (max_high - value) / range_size if range_size > 0 else 1.0
            return 25.0 * position

    def _calculate_ownership_score_with_thresholds(self, value: float, min_threshold: float, max_threshold: float) -> float:
        """
        Calculate institutional ownership score using custom thresholds.

        Sweet spot (min-max): 100
        Under-owned (< min): 50-100 (interpolated)
        Over-owned (> max): 0-50 (interpolated down to 0 at 100% ownership)
        """
        if value is None:
            return 75.0  # Neutral

        # Safety defaults
        min_threshold = min_threshold if min_threshold is not None else 0.20
        max_threshold = max_threshold if max_threshold is not None else 0.60

        if min_threshold <= value <= max_threshold:
            return 100.0  # Sweet spot
        elif value < min_threshold:
            # Under-owned: 50-100 interpolated
            return 50.0 + (value / min_threshold) * 50.0 if min_threshold > 0 else 100.0
        else:
            # Over-owned: 0-50 interpolated (dips to 0 at 100% ownership)
            range_size = 1.0 - max_threshold
            if range_size > 0:
                position = (1.0 - value) / range_size
                return max(0.0, 50.0 * position)
            return 0.0
