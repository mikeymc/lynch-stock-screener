# ABOUTME: Character-aware stock evaluation engine
# ABOUTME: Scores stocks based on the active character's metrics and weights

import logging
import pandas as pd
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

    def evaluate_stock(self, symbol: str, overrides: Dict[str, Any] = None, custom_metrics: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Evaluate a stock using the character's scoring configuration.

        Args:
            symbol: Stock ticker
            overrides: Optional dictionary of weight/threshold overrides
            custom_metrics: Optional pre-calculated metrics (e.g., from backtester)

        Returns:
            Dictionary with evaluation results including overall_score, rating, and breakdown
        """
        
        # Get base metrics
        if custom_metrics:
            base_data = custom_metrics
        else:
            base_data = self._get_base_metrics(symbol)
            if not base_data:
                return None

            # Calculate character-specific metrics
            character_metrics = self._get_character_metrics(symbol)

            # Merge into base data
            base_data.update(character_metrics)

        # Calculate weighted score
        return self._evaluate_weighted(base_data, overrides)

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
            if raw_value is None or pd.isna(raw_value):
                return None
            return max(0.0, 100.0 - (raw_value * 2.0))

        consistency_score = normalize_consistency(raw_income_consistency)

        # Calculate 52-week P/E range
        pe_range_data = self.metric_calculator.calculate_pe_52_week_range(symbol, metrics)

        return {
            'symbol': symbol,
            'company_name': metrics.get('company_name'),
            'sector': metrics.get('sector'),
            'market_cap': metrics.get('market_cap'),
            'price': metrics.get('price'),
            'price_change_pct': metrics.get('price_change_pct'),
            'pe_ratio': metrics.get('pe_ratio'),
            'peg_ratio': metrics.get('peg_ratio'),
            'debt_to_equity': metrics.get('debt_to_equity'),
            'debt_to_earnings': metrics.get('debt_to_earnings'),
            'owner_earnings': metrics.get('owner_earnings'),
            'institutional_ownership': metrics.get('institutional_ownership'),
            'dividend_yield': metrics.get('dividend_yield'),
            'earnings_cagr': earnings_cagr,
            'revenue_cagr': revenue_cagr,
            'earnings_consistency': consistency_score,
            'pe_52_week_min': pe_range_data.get('pe_52_week_min'),
            'pe_52_week_max': pe_range_data.get('pe_52_week_max'),
            'pe_52_week_position': pe_range_data.get('pe_52_week_position'),
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

        if 'gross_margin' in needed_metrics:
            gm_data = self.metric_calculator.calculate_gross_margin(symbol)
            result['gross_margin'] = gm_data.get('current')

        return result

    def _evaluate_weighted(self, base_data: Dict[str, Any], overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        """Calculate weighted score based on character's configuration."""
        component_scores = {}
        breakdown = {}
        total_score = 0.0
        total_weight = 0.0

        for sw in self.character.scoring_weights:
            # Determine weight
            weight_key = f"weight_{sw.metric}"
            weight = overrides.get(weight_key, sw.weight) if overrides else sw.weight

            # Determine threshold
            threshold = sw.threshold
            if overrides:
                 t_excellent = overrides.get(f"{sw.metric}_excellent")
                 t_good = overrides.get(f"{sw.metric}_good")
                 t_fair = overrides.get(f"{sw.metric}_fair")
                 
                 if t_excellent is not None or t_good is not None or t_fair is not None:
                     # Create new Threshold with overrides, falling back to character defaults if override is None
                     threshold = Threshold(
                         excellent=t_excellent if t_excellent is not None else threshold.excellent,
                         good=t_good if t_good is not None else threshold.good,
                         fair=t_fair if t_fair is not None else threshold.fair,
                         lower_is_better=threshold.lower_is_better
                     )

            metric_value = base_data.get(sw.metric)
            score = self._calculate_metric_score(metric_value, threshold, sw.metric)

            component_scores[f'{sw.metric}_score'] = score
            contribution = score * weight
            breakdown[f'{sw.metric}_contribution'] = round(contribution, 1)

            total_score += contribution
            total_weight += weight

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

    def _calculate_metric_score(self, value: Optional[float], threshold: Threshold, metric_id: str) -> float:
        """Calculate 0-100 score for a metric value based on threshold config.

        Scoring pattern:
        - Value better than 'excellent' → 100
        - Value between 'excellent' and 'good' → 75-100 (interpolated)
        - Value between 'good' and 'fair' → 25-75 (interpolated)
        - Value worse than 'fair' → 0-25 (interpolated)
        """
        if value is None or (isinstance(value, float) and pd.isna(value)):
            # Alignment with ScoringMixin: 
            # Missing debt is good (100), missing growth/equity is neutral (0 or 50)
            if threshold.lower_is_better and 'debt' in metric_id:
                return 100.0
            if 'ownership' in metric_id:
                return 75.0
            return 0.0

        if threshold.lower_is_better:
            # For metrics like PEG, debt where lower is better
            return self._score_lower_is_better(value, threshold)
        else:
            # For metrics like ROE where higher is better
            return self._score_higher_is_better(value, threshold)

    def _score_lower_is_better(self, value: float, t: Threshold) -> float:
        """Score a metric where lower values are better (e.g., PEG, debt)."""
        excellent = t.excellent if t.excellent is not None else 1.0
        good = t.good if t.good is not None else 1.5
        fair = t.fair if t.fair is not None else 2.0
        
        if value <= excellent:
            return 100.0
        elif value <= good:
            # 75-100 range
            range_size = good - excellent
            if range_size == 0:
                return 87.5
            position = (good - value) / range_size
            return 75.0 + (25.0 * position)
        elif value <= fair:
            # 25-75 range
            range_size = fair - good
            if range_size == 0:
                return 50.0
            position = (fair - value) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 2x fair
            max_poor = fair * 2
            if value >= max_poor:
                return 0.0
            range_size = max_poor - fair
            if range_size == 0:
                return 12.5
            position = (max_poor - value) / range_size
            return 25.0 * position

    def _score_higher_is_better(self, value: float, t: Threshold) -> float:
        """Score a metric where higher values are better (e.g., ROE, growth)."""
        excellent = t.excellent if t.excellent is not None else 20.0
        good = t.good if t.good is not None else 15.0
        fair = t.fair if t.fair is not None else 10.0
        
        if value >= excellent:
            return 100.0
        elif value >= good:
            # 75-100 range
            range_size = excellent - good
            if range_size == 0:
                return 87.5
            position = (value - good) / range_size
            return 75.0 + (25.0 * position)
        elif value >= fair:
            # 25-75 range
            range_size = good - fair
            if range_size == 0:
                return 50.0
            position = (value - fair) / range_size
            return 25.0 + (50.0 * position)
        else:
            # 0-25 range, cap at 0
            min_poor = 0.0
            if value <= min_poor:
                return 0.0
            range_size = fair - min_poor
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
