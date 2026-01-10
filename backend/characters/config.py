# ABOUTME: Defines CharacterConfig dataclass for investment philosophy personas
# ABOUTME: Each character has prompts, scoring weights, thresholds, and display preferences

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Threshold:
    """Defines scoring thresholds for a metric.

    Scoring works as follows:
    - Value better than 'excellent' threshold → 100 points
    - Value between 'excellent' and 'good' → 75-100 points (interpolated)
    - Value between 'good' and 'fair' → 25-75 points (interpolated)
    - Value worse than 'fair' threshold → 0-25 points (interpolated to minimum)

    For 'lower_is_better' metrics (like debt), the comparisons are reversed.
    """
    excellent: float
    good: float
    fair: float
    lower_is_better: bool = True  # True for PEG, debt; False for ROE, growth


@dataclass
class ScoringWeight:
    """A metric with its weight in the overall score."""
    metric: str  # e.g., 'peg', 'roe', 'debt_to_equity', 'earnings_consistency'
    weight: float  # 0.0 to 1.0, all weights should sum to 1.0
    threshold: Threshold


@dataclass
class CharacterConfig:
    """Configuration for an investment philosophy character.

    Defines how a character (Lynch, Buffett, etc.) analyzes and scores stocks.
    """
    # Identity
    id: str  # e.g., 'lynch', 'buffett'
    name: str  # e.g., 'Peter Lynch', 'Warren Buffett'
    short_description: str  # One-line summary for UI

    # Prompt file paths (relative to backend/prompts/)
    persona_prompt: str  # e.g., 'agent/personas/lynch.md'
    checklist_prompt: str  # e.g., 'analysis/lynch_checklist.md'
    analysis_template: str  # e.g., 'analysis/lynch_full_analysis.md'

    # Scoring configuration
    scoring_weights: List[ScoringWeight] = field(default_factory=list)

    # Display configuration
    primary_metrics: List[str] = field(default_factory=list)  # Metrics to show prominently
    secondary_metrics: List[str] = field(default_factory=list)  # Metrics to show in detail view
    hidden_metrics: List[str] = field(default_factory=list)  # Metrics to hide (not relevant to this character)

    # Algorithm variants this character supports
    # Most characters use 'weighted', but some may support category-based or other variants
    supported_algorithms: List[str] = field(default_factory=lambda: ['weighted'])
    default_algorithm: str = 'weighted'

    def get_weight(self, metric: str) -> Optional[float]:
        """Get the weight for a specific metric, or None if not used."""
        for sw in self.scoring_weights:
            if sw.metric == metric:
                return sw.weight
        return None

    def get_threshold(self, metric: str) -> Optional[Threshold]:
        """Get the threshold configuration for a specific metric."""
        for sw in self.scoring_weights:
            if sw.metric == metric:
                return sw.threshold
        return None

    def validate(self) -> List[str]:
        """Validate the configuration. Returns list of error messages."""
        errors = []

        # Check weights sum to 1.0 (within floating point tolerance)
        total_weight = sum(sw.weight for sw in self.scoring_weights)
        if abs(total_weight - 1.0) > 0.01:
            errors.append(f"Scoring weights sum to {total_weight}, should be 1.0")

        # Check for duplicate metrics
        metrics = [sw.metric for sw in self.scoring_weights]
        if len(metrics) != len(set(metrics)):
            errors.append("Duplicate metrics in scoring_weights")

        return errors
