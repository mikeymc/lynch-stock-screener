# ABOUTME: Character-aware stock evaluation engine
# ABOUTME: Scores stocks based on the active character's metrics and weights

import logging
from typing import Dict, Any, Optional, List

from database import Database
from earnings_analyzer import EarningsAnalyzer
from characters.config import CharacterConfig, Threshold, ScoringWeight
from metric_calculator import MetricCalculator

logger = logging.getLogger(__name__)


class StockEvaluator:
    """Evaluates stocks using character-specific criteria.

    This is a character-aware version of the scoring logic from LynchCriteria.
    It uses a CharacterConfig to determine which metrics matter and how to weight them.
    """

    def __init__(self, db: Database, analyzer: EarningsAnalyzer, character: CharacterConfig):
        self.db = db
        self.analyzer = analyzer
        self.character = character
        self.metric_calculator = MetricCalculator(db)

    def evaluate_stock(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Evaluate a stock using the character's scoring configuration.

        Returns:
            Dictionary with evaluation results including overall_score, rating, and breakdown
        """
        # Get base metrics
        base_data = self._get_base_metrics(symbol)
        if not base_data:
            return None

        # Calculate character-specific metrics
        character_metrics = self._get_character_metrics(symbol)

        # Merge into base data
        base_data.update(character_metrics)

        # Calculate weighted score
        return self._evaluate_weighted(base_data)

    def _get_base_metrics(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get base metrics from database."""
        metrics = self.db.get_stock_metrics(symbol)
        if not metrics:
            return None

        growth_data = self.analyzer.calculate_earnings_growth(symbol)

        # Extract growth data
        earnings_cagr = growth_data['earnings_cagr'] if growth_data else None
        revenue_cagr = growth_data['revenue_cagr'] if growth_data else None

        # Normalize consistency scores to 0-100 scale
        raw_income_consistency = growth_data.get('income_consistency_score') if growth_data else None

        def normalize_consistency(raw_value):
            if raw_value is None:
                return None
            return max(0.0, 100.0 - (raw_value * 2.0))

        consistency_score = normalize_consistency(raw_income_consistency)

        return {
            'symbol': symbol,
            'company_name': metrics.get('company_name'),
            'sector': metrics.get('sector'),
            'market_cap': metrics.get('market_cap'),
            'price': metrics.get('price'),
            'pe_ratio': metrics.get('pe_ratio'),
            'peg_ratio': metrics.get('peg_ratio'),
            'debt_to_equity': metrics.get('debt_to_equity'),
            'institutional_ownership': metrics.get('institutional_ownership'),
            'dividend_yield': metrics.get('dividend_yield'),
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'earnings_consistency': consistency_score,
        }

    def _get_character_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get metrics specific to this character."""
        result = {}

        # Check which metrics this character needs
        needed_metrics = {sw.metric for sw in self.character.scoring_weights}

        if 'roe' in needed_metrics:
            roe_data = self.metric_calculator.calculate_roe(symbol)
            result['roe'] = roe_data.get('current_roe')
            result['roe_5yr_avg'] = roe_data.get('avg_roe_5yr')
            result['roe_10yr_avg'] = roe_data.get('avg_roe_10yr')

        if 'debt_to_earnings' in needed_metrics:
            debt_data = self.metric_calculator.calculate_debt_to_earnings(symbol)
            result['debt_to_earnings'] = debt_data.get('debt_to_earnings_years')

        if 'owner_earnings' in needed_metrics:
            oe_data = self.metric_calculator.calculate_owner_earnings(symbol)
            result['owner_earnings'] = oe_data.get('owner_earnings')

        return result

    def _evaluate_weighted(self, base_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate weighted score based on character's configuration."""
        component_scores = {}
        breakdown = {}
        total_score = 0.0
        total_weight = 0.0

        for sw in self.character.scoring_weights:
            metric_value = base_data.get(sw.metric)
            score = self._calculate_metric_score(metric_value, sw.threshold)

            component_scores[f'{sw.metric}_score'] = score
            contribution = score * sw.weight
            breakdown[f'{sw.metric}_contribution'] = round(contribution, 1)

            total_score += contribution
            total_weight += sw.weight

        # Normalize if weights don't sum to 1.0 (shouldn't happen, but safe)
        if total_weight > 0 and abs(total_weight - 1.0) > 0.01:
            total_score = total_score / total_weight

        # Determine rating based on score
        overall_status, rating_label = self._score_to_rating(total_score)

        result = base_data.copy()
        result['character'] = self.character.id
        result['character_name'] = self.character.name
        result['algorithm'] = 'weighted'
        result['overall_score'] = round(total_score, 1)
        result['overall_status'] = overall_status
        result['rating_label'] = rating_label
        result['breakdown'] = breakdown
        result.update(component_scores)

        return result

    def _calculate_metric_score(self, value: Optional[float], threshold: Threshold) -> float:
        """Calculate 0-100 score for a metric value based on threshold config.

        Scoring pattern:
        - Value better than 'excellent' → 100
        - Value between 'excellent' and 'good' → 75-100 (interpolated)
        - Value between 'good' and 'fair' → 25-75 (interpolated)
        - Value worse than 'fair' → 0-25 (interpolated)
        """
        if value is None:
            return 0.0

        if threshold.lower_is_better:
            # For metrics like PEG, debt where lower is better
            return self._score_lower_is_better(value, threshold)
        else:
            # For metrics like ROE where higher is better
            return self._score_higher_is_better(value, threshold)

    def _score_lower_is_better(self, value: float, t: Threshold) -> float:
        """Score a metric where lower values are better (e.g., PEG, debt)."""
        if value <= t.excellent:
            return 100.0
        elif value <= t.good:
            # 75-100 range
            range_size = t.good - t.excellent
            if range_size == 0:
                return 87.5
            position = (t.good - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= t.fair:
            # 25-75 range
            range_size = t.fair - t.good
            if range_size == 0:
                return 50.0
            position = (t.fair - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 2x fair
            max_poor = t.fair * 2
            if value >= max_poor:
                return 0.0
            range_size = max_poor - t.fair
            if range_size == 0:
                return 12.5
            position = (max_poor - value) / range_size
            return 25.0 * position

    def _score_higher_is_better(self, value: float, t: Threshold) -> float:
        """Score a metric where higher values are better (e.g., ROE, growth)."""
        if value >= t.excellent:
            return 100.0
        elif value >= t.good:
            # 75-100 range
            range_size = t.excellent - t.good
            if range_size == 0:
                return 87.5
            position = (value - t.good) / range_size
            return 75.0 + (25.0 * position)
        elif value >= t.fair:
            # 25-75 range
            range_size = t.good - t.fair
            if range_size == 0:
                return 50.0
            position = (value - t.fair) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 0
            min_poor = 0.0
            if value <= min_poor:
                return 0.0
            range_size = t.fair - min_poor
            if range_size == 0:
                return 12.5
            position = value / range_size
            return 25.0 * position

    def _score_to_rating(self, score: float) -> tuple:
        """Convert numeric score to rating label and status."""
        if score >= 80:
            return ("STRONG_BUY", "STRONG BUY")
        elif score >= 60:
            return ("BUY", "BUY")
        elif score >= 40:
            return ("HOLD", "HOLD")
        elif score >= 20:
            return ("CAUTION", "CAUTION")
        else:
            return ("AVOID", "AVOID")


def evaluate_stock_with_character(
    db: Database,
    analyzer: EarningsAnalyzer,
    symbol: str,
    character_id: str = 'lynch'
) -> Optional[Dict[str, Any]]:
    """Convenience function to evaluate a stock with a specific character.

    Args:
        db: Database instance
        analyzer: EarningsAnalyzer instance
        symbol: Stock ticker
        character_id: Character to use (default 'lynch')

    Returns:
        Evaluation results or None if stock not found
    """
    from characters import get_character

    character = get_character(character_id)
    if not character:
        logger.error(f"Character not found: {character_id}")
        return None

    evaluator = StockEvaluator(db, analyzer, character)
    return evaluator.evaluate_stock(symbol)
