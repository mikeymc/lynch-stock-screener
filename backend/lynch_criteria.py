# ABOUTME: Evaluates stocks against Peter Lynch investment criteria
# ABOUTME: Flags stocks as PASS, CLOSE, or FAIL based on PEG ratio, debt, growth, and ownership

from typing import Dict, Any, Optional
from database import Database
from earnings_analyzer import EarningsAnalyzer


# Algorithm metadata for UI display
ALGORITHM_METADATA = {
    'weighted': {
        'name': 'Weighted Scoring',
        'short_desc': 'Balanced approach weighting PEG ratio most heavily with earnings quality',
        'description': '''Assigns weighted importance to each metric based on Lynch's priorities:
        • PEG Ratio: 50% (Lynch's primary valuation metric)
        • Earnings Consistency: 25% (quality of growth matters)
        • Debt-to-Equity: 15% (important but contextual)
        • Institutional Ownership: 10% (minor consideration)

        Produces a 0-100 score: Strong Buy (80+), Buy (60-80), Hold (40-60), Caution (20-40), Avoid (0-20).
        Best for: Balanced evaluation that prioritizes what Lynch cared about most.''',
        'recommended': True
    },
    'two_tier': {
        'name': 'Two-Tier System',
        'short_desc': 'Must-have deal-breakers plus nice-to-have scoring for quality checks',
        'description': '''First checks critical deal-breakers, then scores on quality metrics:

        Must-Have Criteria (automatic AVOID if failed):
        • PEG Ratio < 2.0 (Lynch's outer limit)
        • Debt-to-Equity < 1.0 (manageable debt)

        Nice-to-Have Scoring (if passed must-haves):
        • PEG < 1.0 (ideal territory)
        • Strong earnings consistency
        • Moderate institutional ownership

        Best for: Conservative investors who want clear deal-breaker rules.''',
        'recommended': False
    },
    'category_based': {
        'name': 'Category-Based',
        'short_desc': 'Different criteria for different stock types (fast growers, stalwarts, etc.)',
        'description': '''Classifies stocks by Lynch's categories, then applies appropriate criteria:

        • Fast Growers: Emphasis on PEG < 1.0, earnings growth, low debt
        • Stalwarts: Allow higher PEG (up to 1.5), focus on consistency
        • Cyclicals: Consider P/E vs historical average, allow more debt
        • Turnarounds: Different criteria focused on improvement trajectory
        • Asset Plays: Focus on book value and asset coverage

        Each category uses different thresholds and weights tailored to that investment type.
        Best for: Sophisticated investors who understand different stock categories.''',
        'recommended': False
    },
    'critical_factors': {
        'name': 'Critical Factors',
        'short_desc': 'Simplified qualitative assessment of only the most important factors',
        'description': '''Simplified approach focusing on Lynch's core principles:

        • PEG acceptability (contextual, not rigid threshold)
        • Positive earnings trend (growth trajectory matters)
        • Manageable debt (industry-relative assessment)
        • The "story" makes sense (qualitative evaluation)

        More qualitative and flexible than pure numbers. Uses broader ranges and contextual judgment.
        Best for: Quick screening and investors who prefer simpler, story-based evaluation.''',
        'recommended': False
    },
    'classic': {
        'name': 'Classic (Original)',
        'short_desc': 'Original rigid pass/fail system requiring all metrics to pass',
        'description': '''The original strict evaluation system:

        • PASS: All three metrics (PEG, Debt, Institutional Ownership) must PASS
        • FAIL: If ANY single metric FAILS, the entire stock FAILS
        • CLOSE: Some metrics PASS, some CLOSE (no FAILs)

        Thresholds: PEG < 1.0, Debt/Equity < 0.5, Institutional < 50%

        Best for: Very conservative screening with strict requirements.
        Note: May be too rigid for Lynch's actual philosophy.''',
        'recommended': False
    }
}


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

    def evaluate_stock(self, symbol: str, algorithm: str = 'weighted') -> Optional[Dict[str, Any]]:
        """
        Evaluate a stock using the specified algorithm.

        Args:
            symbol: Stock ticker symbol
            algorithm: One of 'weighted', 'two_tier', 'category_based', 'critical_factors', 'classic'

        Returns:
            Dictionary with evaluation results including algorithm-specific scoring
        """
        # Get base metrics and growth data
        base_data = self._get_base_metrics(symbol)
        if not base_data:
            return None

        # Route to appropriate algorithm
        if algorithm == 'weighted':
            return self._evaluate_weighted(symbol, base_data)
        elif algorithm == 'two_tier':
            return self._evaluate_two_tier(symbol, base_data)
        elif algorithm == 'category_based':
            return self._evaluate_category_based(symbol, base_data)
        elif algorithm == 'critical_factors':
            return self._evaluate_critical_factors(symbol, base_data)
        elif algorithm == 'classic':
            return self._evaluate_classic(symbol, base_data)
        else:
            # Default to weighted if unknown algorithm
            return self._evaluate_weighted(symbol, base_data)

    def _get_base_metrics(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get base metrics and growth data for a stock."""
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

        # Calculate individual metric scores
        if peg_ratio is None:
            peg_status = "FAIL"
            peg_score = 0.0
        else:
            peg_status = self.evaluate_criterion(peg_ratio, self.PEG_IDEAL, self.PEG_CLOSE, lower_is_better=True)
            peg_score = self.calculate_metric_score(peg_ratio, self.PEG_IDEAL, self.PEG_CLOSE, lower_is_better=True)

        debt_status = self.evaluate_criterion(debt_to_equity, self.DEBT_TO_EQUITY_IDEAL, self.DEBT_TO_EQUITY_CLOSE, lower_is_better=True)
        debt_score = self.calculate_metric_score(debt_to_equity, self.DEBT_TO_EQUITY_IDEAL, self.DEBT_TO_EQUITY_CLOSE, lower_is_better=True)

        inst_ownership_status = self.evaluate_criterion(institutional_ownership, self.INSTITUTIONAL_OWNERSHIP_IDEAL, self.INSTITUTIONAL_OWNERSHIP_CLOSE, lower_is_better=True)
        inst_ownership_score = self.calculate_metric_score(institutional_ownership, self.INSTITUTIONAL_OWNERSHIP_IDEAL, self.INSTITUTIONAL_OWNERSHIP_CLOSE, lower_is_better=True)

        # Return base data that all algorithms can use
        return {
            'metrics': metrics,
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
        }

    def _evaluate_classic(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Original strict pass/fail algorithm - all metrics must pass."""
        statuses = [base_data['peg_status'], base_data['debt_status'], base_data['institutional_ownership_status']]

        if all(s == "PASS" for s in statuses):
            overall_status = "PASS"
        elif any(s == "FAIL" for s in statuses):
            overall_status = "FAIL"
        else:
            overall_status = "CLOSE"

        result = base_data.copy()
        result['algorithm'] = 'classic'
        result['overall_status'] = overall_status
        result['overall_score'] = self._status_to_score(overall_status)
        result['rating_label'] = overall_status
        return result

    def _evaluate_weighted(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Weighted scoring: PEG 50%, Consistency 25%, Debt 15%, Ownership 10%."""
        # Calculate weighted score
        peg_weight = 0.50
        consistency_weight = 0.25
        debt_weight = 0.15
        ownership_weight = 0.10

        # Get consistency score (0-100), default to 50 if not available
        consistency_score = base_data.get('consistency_score', 50) if base_data.get('consistency_score') is not None else 50

        # Calculate weighted overall score
        overall_score = (
            base_data['peg_score'] * peg_weight +
            consistency_score * consistency_weight +
            base_data['debt_score'] * debt_weight +
            base_data['institutional_ownership_score'] * ownership_weight
        )

        # Determine rating based on score
        if overall_score >= 80:
            rating_label = "STRONG BUY"
            overall_status = "STRONG_BUY"
        elif overall_score >= 60:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 40:
            rating_label = "HOLD"
            overall_status = "HOLD"
        elif overall_score >= 20:
            rating_label = "CAUTION"
            overall_status = "CAUTION"
        else:
            rating_label = "AVOID"
            overall_status = "AVOID"

        result = base_data.copy()
        result['algorithm'] = 'weighted'
        result['overall_score'] = round(overall_score, 1)
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['breakdown'] = {
            'peg_contribution': round(base_data['peg_score'] * peg_weight, 1),
            'consistency_contribution': round(consistency_score * consistency_weight, 1),
            'debt_contribution': round(base_data['debt_score'] * debt_weight, 1),
            'ownership_contribution': round(base_data['institutional_ownership_score'] * ownership_weight, 1)
        }
        return result

    def _evaluate_two_tier(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Two-tier: Must-have criteria first, then nice-to-have scoring."""
        # Must-have criteria (deal breakers)
        peg_ratio = base_data.get('peg_ratio')
        debt_to_equity = base_data.get('debt_to_equity', 0)

        # Check deal breakers
        deal_breakers = []
        if peg_ratio is None or peg_ratio > 2.0:
            deal_breakers.append('PEG > 2.0')
        if debt_to_equity > 1.0:
            deal_breakers.append('Debt/Equity > 1.0')

        if deal_breakers:
            # Failed must-haves = automatic AVOID
            result = base_data.copy()
            result['algorithm'] = 'two_tier'
            result['overall_score'] = 0
            result['overall_status'] = 'AVOID'
            result['rating_label'] = 'AVOID'
            result['breakdown'] = {
                'passed_must_haves': False,
                'deal_breakers': deal_breakers
            }
            return result

        # Passed must-haves, now score on nice-to-haves
        # PEG < 1.0: 40 points, Consistency: 30 points, Ownership: 30 points
        peg_nice_score = 40 if peg_ratio <= 1.0 else max(0, 40 * (2.0 - peg_ratio) / 1.0)
        consistency_score = base_data.get('consistency_score', 50) if base_data.get('consistency_score') is not None else 50
        consistency_nice_score = (consistency_score / 100) * 30
        ownership_nice_score = (base_data['institutional_ownership_score'] / 100) * 30

        overall_score = peg_nice_score + consistency_nice_score + ownership_nice_score

        # Determine rating
        if overall_score >= 80:
            rating_label = "STRONG BUY"
            overall_status = "STRONG_BUY"
        elif overall_score >= 60:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 40:
            rating_label = "HOLD"
            overall_status = "HOLD"
        else:
            rating_label = "CAUTION"
            overall_status = "CAUTION"

        result = base_data.copy()
        result['algorithm'] = 'two_tier'
        result['overall_score'] = round(overall_score, 1)
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['breakdown'] = {
            'passed_must_haves': True,
            'peg_nice_score': round(peg_nice_score, 1),
            'consistency_nice_score': round(consistency_nice_score, 1),
            'ownership_nice_score': round(ownership_nice_score, 1)
        }
        return result

    def _evaluate_category_based(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Category-based: Classify stock type, then apply appropriate criteria."""
        # Classify stock category based on Lynch's categories
        earnings_cagr = base_data.get('earnings_cagr')
        revenue_cagr = base_data.get('revenue_cagr')
        peg_ratio = base_data.get('peg_ratio')
        debt_to_equity = base_data.get('debt_to_equity', 0)
        dividend_yield = base_data.get('dividend_yield', 0)

        # Simple category classification logic
        category = self._classify_stock_category(earnings_cagr, revenue_cagr, dividend_yield, base_data.get('market_cap'))

        # Apply category-specific scoring
        if category == 'fast_grower':
            # Fast Growers: Emphasize PEG < 1.0, high growth, low debt
            peg_threshold = 1.0
            debt_threshold = 0.4
            peg_weight = 0.60
            growth_weight = 0.30
            debt_weight = 0.10
        elif category == 'stalwart':
            # Stalwarts: Allow higher PEG, focus on consistency
            peg_threshold = 1.5
            debt_threshold = 0.6
            peg_weight = 0.40
            growth_weight = 0.40
            debt_weight = 0.20
        elif category == 'cyclical':
            # Cyclicals: Allow more debt, focus on current valuation
            peg_threshold = 1.2
            debt_threshold = 0.8
            peg_weight = 0.50
            growth_weight = 0.20
            debt_weight = 0.30
        else:  # slow_grower or other
            # Conservative approach
            peg_threshold = 1.0
            debt_threshold = 0.5
            peg_weight = 0.50
            growth_weight = 0.25
            debt_weight = 0.25

        # Calculate category-specific scores
        peg_category_score = 100 if peg_ratio and peg_ratio <= peg_threshold else (base_data['peg_score'] * 0.8)
        debt_category_score = 100 if debt_to_equity <= debt_threshold else (base_data['debt_score'] * 0.8)
        consistency_score = base_data.get('consistency_score', 50) if base_data.get('consistency_score') is not None else 50

        overall_score = (
            peg_category_score * peg_weight +
            consistency_score * growth_weight +
            debt_category_score * debt_weight
        )

        # Determine rating
        if overall_score >= 80:
            rating_label = "STRONG BUY"
            overall_status = "STRONG_BUY"
        elif overall_score >= 60:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 40:
            rating_label = "HOLD"
            overall_status = "HOLD"
        elif overall_score >= 20:
            rating_label = "CAUTION"
            overall_status = "CAUTION"
        else:
            rating_label = "AVOID"
            overall_status = "AVOID"

        result = base_data.copy()
        result['algorithm'] = 'category_based'
        result['overall_score'] = round(overall_score, 1)
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['stock_category'] = category
        result['breakdown'] = {
            'category': category,
            'peg_threshold': peg_threshold,
            'debt_threshold': debt_threshold,
            'peg_contribution': round(peg_category_score * peg_weight, 1),
            'growth_contribution': round(consistency_score * growth_weight, 1),
            'debt_contribution': round(debt_category_score * debt_weight, 1)
        }
        return result

    def _evaluate_critical_factors(self, symbol: str, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Critical factors: Simplified qualitative assessment."""
        peg_ratio = base_data.get('peg_ratio')
        earnings_cagr = base_data.get('earnings_cagr')
        debt_to_equity = base_data.get('debt_to_equity', 0)

        # Simple scoring based on critical factors
        score_components = []
        reasons = []

        # Factor 1: PEG acceptability (0-40 points)
        if peg_ratio is None:
            peg_points = 0
            reasons.append("No PEG ratio available")
        elif peg_ratio <= 1.0:
            peg_points = 40
            reasons.append(f"Excellent PEG ratio ({peg_ratio:.2f})")
        elif peg_ratio <= 1.5:
            peg_points = 30
            reasons.append(f"Good PEG ratio ({peg_ratio:.2f})")
        elif peg_ratio <= 2.0:
            peg_points = 20
            reasons.append(f"Acceptable PEG ratio ({peg_ratio:.2f})")
        else:
            peg_points = 0
            reasons.append(f"High PEG ratio ({peg_ratio:.2f})")

        # Factor 2: Earnings trend (0-35 points)
        if earnings_cagr is None:
            earnings_points = 15
            reasons.append("No earnings growth data")
        elif earnings_cagr >= 20:
            earnings_points = 35
            reasons.append(f"Strong earnings growth ({earnings_cagr:.1f}%)")
        elif earnings_cagr >= 10:
            earnings_points = 25
            reasons.append(f"Good earnings growth ({earnings_cagr:.1f}%)")
        elif earnings_cagr > 0:
            earnings_points = 15
            reasons.append(f"Positive earnings growth ({earnings_cagr:.1f}%)")
        else:
            earnings_points = 0
            reasons.append(f"Negative earnings growth ({earnings_cagr:.1f}%)")

        # Factor 3: Manageable debt (0-25 points)
        if debt_to_equity <= 0.3:
            debt_points = 25
            reasons.append(f"Minimal debt ({debt_to_equity:.2f})")
        elif debt_to_equity <= 0.6:
            debt_points = 20
            reasons.append(f"Moderate debt ({debt_to_equity:.2f})")
        elif debt_to_equity <= 1.0:
            debt_points = 10
            reasons.append(f"Elevated debt ({debt_to_equity:.2f})")
        else:
            debt_points = 0
            reasons.append(f"High debt ({debt_to_equity:.2f})")

        overall_score = peg_points + earnings_points + debt_points

        # Simple rating
        if overall_score >= 75:
            rating_label = "BUY"
            overall_status = "BUY"
        elif overall_score >= 50:
            rating_label = "HOLD"
            overall_status = "HOLD"
        else:
            rating_label = "AVOID"
            overall_status = "AVOID"

        result = base_data.copy()
        result['algorithm'] = 'critical_factors'
        result['overall_score'] = overall_score
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['breakdown'] = {
            'peg_points': peg_points,
            'earnings_points': earnings_points,
            'debt_points': debt_points,
            'reasons': reasons
        }
        return result

    def _classify_stock_category(self, earnings_cagr, revenue_cagr, dividend_yield, market_cap):
        """Classify stock into Lynch's categories."""
        if earnings_cagr is None:
            return 'unknown'

        # Fast Grower: High growth (20%+), usually smaller companies
        if earnings_cagr >= 20:
            return 'fast_grower'
        # Stalwart: Moderate growth (10-20%), usually large established companies
        elif earnings_cagr >= 10:
            return 'stalwart'
        # Slow Grower: Low growth (<10%), often pays dividends
        elif earnings_cagr >= 0:
            return 'slow_grower'
        # Potential turnaround: Negative growth
        else:
            return 'turnaround'

    def _status_to_score(self, status: str) -> float:
        """Convert old PASS/CLOSE/FAIL status to numeric score for compatibility."""
        if status == "PASS":
            return 80.0
        elif status == "CLOSE":
            return 60.0
        else:
            return 20.0

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

    def calculate_metric_score(self, value: float, ideal_threshold: float, close_threshold: float, lower_is_better: bool = True) -> float:
        """
        Calculate a 0-100 score showing position within pass/close/fail ranges.
        100 = perfect (ideal threshold), 0 = worst
        """
        if value is None:
            return 0.0

        if lower_is_better:
            # Perfect score at or below ideal threshold
            if value <= ideal_threshold:
                return 100.0
            # Score 75-100 between ideal and close
            elif value <= close_threshold:
                range_size = close_threshold - ideal_threshold
                position = (close_threshold - value) / range_size if range_size > 0 else 0
                return 75.0 + (25.0 * position)
            # Score 0-75 in fail zone (estimate fail zone as 2x close threshold)
            else:
                fail_estimate = close_threshold * 2
                if value <= fail_estimate:
                    range_size = fail_estimate - close_threshold
                    position = (fail_estimate - value) / range_size if range_size > 0 else 0
                    return 50.0 * position
                else:
                    return 0.0
        else:
            # For "higher is better" metrics
            if value >= ideal_threshold:
                return 100.0
            elif value >= close_threshold:
                range_size = ideal_threshold - close_threshold
                position = (value - close_threshold) / range_size if range_size > 0 else 0
                return 75.0 + (25.0 * position)
            else:
                # Estimate fail zone
                fail_estimate = close_threshold / 2
                if value >= fail_estimate:
                    range_size = close_threshold - fail_estimate
                    position = (value - fail_estimate) / range_size if range_size > 0 else 0
                    return 50.0 * position
                else:
                    return 0.0
