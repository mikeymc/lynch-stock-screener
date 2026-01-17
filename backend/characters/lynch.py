# ABOUTME: Peter Lynch character configuration
# ABOUTME: Growth at a reasonable price (GARP) investment philosophy

from .config import CharacterConfig, ScoringWeight, Threshold
from .loader import register_character

LYNCH = CharacterConfig(
    id='lynch',
    name='Peter Lynch',
    short_description='Growth at a reasonable price. PEG ratio obsessed.',

    # Prompt files
    persona_prompt='agent/personas/lynch.md',
    checklist_prompt='analysis/lynch_checklist.md',
    analysis_template='analysis/lynch_full_analysis.md',

    # Scoring weights (must sum to 1.0)
    # These match the current defaults in lynch_criteria.py
    scoring_weights=[
        ScoringWeight(
            metric='peg',
            weight=0.50,
            threshold=Threshold(
                excellent=1.0,  # PEG < 1.0 is excellent
                good=1.5,       # PEG < 1.5 is good
                fair=2.0,       # PEG < 2.0 is fair
                lower_is_better=True,
            ),
        ),
        ScoringWeight(
            metric='earnings_consistency',
            weight=0.25,
            threshold=Threshold(
                excellent=80.0,  # Consistency score 80+ is excellent
                good=60.0,       # 60+ is good
                fair=40.0,       # 40+ is fair
                lower_is_better=False,
            ),
        ),
        ScoringWeight(
            metric='debt_to_equity',
            weight=0.15,
            threshold=Threshold(
                excellent=0.5,  # D/E < 0.5 is excellent
                good=1.0,       # D/E < 1.0 is good
                fair=2.0,       # D/E < 2.0 is fair
                lower_is_better=True,
            ),
        ),
        ScoringWeight(
            metric='institutional_ownership',
            weight=0.10,
            threshold=Threshold(
                excellent=0.40,  # ~40% is the sweet spot
                good=0.30,       # 30% is good
                fair=0.20,       # 20% is acceptable
                lower_is_better=False,  # Special: actually a sweet spot, not linear
            ),
        ),
    ],

    # Display preferences
    primary_metrics=[
        'peg_ratio',
        'pe_ratio',
        'debt_to_equity',
        'institutional_ownership',
    ],
    secondary_metrics=[
        'earnings_cagr',
        'revenue_cagr',
        'earnings_consistency',
        'free_cash_flow',
    ],
    hidden_metrics=[
        'roe',  # Lynch doesn't emphasize ROE
        'owner_earnings',  # Buffett metric
    ],

    supported_algorithms=['weighted'],
    default_algorithm='weighted',
)

# Register on import
register_character(LYNCH)
