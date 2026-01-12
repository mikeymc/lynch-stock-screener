# ABOUTME: Applies character-specific scoring to stock screening results on the fly
# ABOUTME: Enables seamless character switching without re-running the screener

import logging
from typing import Dict, Any, List, Optional
from characters.config import CharacterConfig, Threshold

logger = logging.getLogger(__name__)


def compute_metric_score(value: float, threshold: Threshold) -> float:
    """Compute a 0-100 score for a metric value based on thresholds.

    Uses linear interpolation between threshold levels:
    - Value better than 'excellent' → 100 points
    - Value between 'excellent' and 'good' → 75-100 points
    - Value between 'good' and 'fair' → 25-75 points
    - Value worse than 'fair' → 0-25 points

    Args:
        value: The metric value to score
        threshold: Threshold configuration with excellent/good/fair levels

    Returns:
        Score from 0-100
    """
    if value is None:
        return 0.0

    if threshold.lower_is_better:
        # For metrics like debt, PEG where lower is better
        if value <= threshold.excellent:
            return 100.0
        elif value <= threshold.good:
            # Interpolate between 75-100
            range_size = threshold.good - threshold.excellent
            if range_size > 0:
                position = (value - threshold.excellent) / range_size
                return 100.0 - (position * 25.0)
            return 75.0
        elif value <= threshold.fair:
            # Interpolate between 25-75
            range_size = threshold.fair - threshold.good
            if range_size > 0:
                position = (value - threshold.good) / range_size
                return 75.0 - (position * 50.0)
            return 25.0
        else:
            # Worse than fair - interpolate 0-25 (capped at 4x fair)
            max_bad = threshold.fair * 2
            if value >= max_bad:
                return 0.0
            range_size = max_bad - threshold.fair
            if range_size > 0:
                position = (value - threshold.fair) / range_size
                return 25.0 - (position * 25.0)
            return 0.0
    else:
        # For metrics like ROE where higher is better
        if value >= threshold.excellent:
            return 100.0
        elif value >= threshold.good:
            # Interpolate between 75-100
            range_size = threshold.excellent - threshold.good
            if range_size > 0:
                position = (threshold.excellent - value) / range_size
                return 100.0 - (position * 25.0)
            return 75.0
        elif value >= threshold.fair:
            # Interpolate between 25-75
            range_size = threshold.good - threshold.fair
            if range_size > 0:
                position = (threshold.good - value) / range_size
                return 75.0 - (position * 50.0)
            return 25.0
        else:
            # Worse than fair - interpolate 0-25
            min_bad = threshold.fair / 2 if threshold.fair > 0 else 0
            if value <= min_bad:
                return 0.0
            range_size = threshold.fair - min_bad
            if range_size > 0:
                position = (threshold.fair - value) / range_size
                return 25.0 - (position * 25.0)
            return 0.0


def score_to_status(score: float) -> str:
    """Convert a 0-100 score to a status string."""
    if score >= 80:
        return "EXCELLENT"
    elif score >= 60:
        return "GOOD"
    elif score >= 40:
        return "FAIR"
    elif score >= 20:
        return "POOR"
    else:
        return "FAIL"


def overall_score_to_status(score: float) -> str:
    """Convert overall score to overall status for display."""
    if score >= 80:
        return "STRONG_BUY"
    elif score >= 60:
        return "BUY"
    elif score >= 40:
        return "HOLD"
    elif score >= 20:
        return "CAUTION"
    else:
        return "AVOID"


def apply_character_scoring(row: Dict[str, Any], character: CharacterConfig) -> Dict[str, Any]:
    """Apply character-specific scoring to a stock row.

    Takes raw metric values from screening_results and computes scores
    based on the character's weights and thresholds.

    Args:
        row: Dictionary with raw stock metrics (peg_ratio, roe, etc.)
        character: CharacterConfig defining weights and thresholds

    Returns:
        New dictionary with computed scores added
    """
    result = dict(row)

    # Compute each metric's score based on character's thresholds
    total_score = 0.0
    total_weight = 0.0

    for sw in character.scoring_weights:
        metric_name = sw.metric
        metric_value = None

        # Map character metric names to row keys
        # Some characters use different names for the same underlying data
        if metric_name == 'peg':
            metric_value = row.get('peg_ratio')
        elif metric_name == 'debt_to_equity':
            metric_value = row.get('debt_to_equity')
        elif metric_name == 'institutional_ownership':
            metric_value = row.get('institutional_ownership')
        elif metric_name == 'earnings_consistency':
            metric_value = row.get('consistency_score')
        elif metric_name == 'roe':
            metric_value = row.get('roe')
        elif metric_name == 'debt_to_earnings':
            metric_value = row.get('debt_to_earnings')
        else:
            # Try direct lookup
            metric_value = row.get(metric_name)

        if metric_value is not None:
            score = compute_metric_score(metric_value, sw.threshold)
            result[f'{metric_name}_score'] = round(score, 1)
            result[f'{metric_name}_status'] = score_to_status(score)
            total_score += score * sw.weight
            total_weight += sw.weight
        else:
            # No data for this metric - don't count it toward total
            result[f'{metric_name}_score'] = None
            result[f'{metric_name}_status'] = None

    result['overall_score'] = round(total_score, 1)
    result['overall_status'] = overall_score_to_status(total_score)

    return result


def apply_character_scoring_batch(
    rows: List[Dict[str, Any]],
    character: CharacterConfig
) -> List[Dict[str, Any]]:
    """Apply character scoring to a batch of stock rows.

    Args:
        rows: List of stock data dictionaries
        character: CharacterConfig to use for scoring

    Returns:
        List of dictionaries with scores added
    """
    return [apply_character_scoring(row, character) for row in rows]
