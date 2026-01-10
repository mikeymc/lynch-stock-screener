# ABOUTME: Warren Buffett character configuration
# ABOUTME: Focus on durable competitive advantage and return on equity

from .config import CharacterConfig, ScoringWeight, Threshold
from .loader import register_character

BUFFETT = CharacterConfig(
    id='buffett',
    name='Warren Buffett',
    short_description='Quality businesses with durable moats. ROE obsessed.',

    # Prompt files
    persona_prompt='agent/personas/buffett.md',
    checklist_prompt='analysis/buffett_checklist.md',
    analysis_template='analysis/buffett_full_analysis.md',

    # Scoring weights (must sum to 1.0)
    scoring_weights=[
        ScoringWeight(
            metric='roe',
            weight=0.40,
            threshold=Threshold(
                excellent=20.0,  # ROE > 20% is excellent
                good=15.0,       # ROE > 15% is good
                fair=10.0,       # ROE > 10% is fair
                lower_is_better=False,
            ),
        ),
        ScoringWeight(
            metric='earnings_consistency',
            weight=0.30,
            threshold=Threshold(
                excellent=80.0,  # Consistent earnings = predictable business
                good=60.0,
                fair=40.0,
                lower_is_better=False,
            ),
        ),
        ScoringWeight(
            metric='debt_to_earnings',
            weight=0.30,
            threshold=Threshold(
                excellent=2.0,   # Can pay off debt in 2 years = excellent
                good=4.0,        # 4 years is good
                fair=7.0,        # 7 years is fair (Buffett's outer limit is ~4)
                lower_is_better=True,
            ),
        ),
    ],

    # Display preferences
    primary_metrics=[
        'roe',
        'owner_earnings',
        'debt_to_earnings',
        'earnings_consistency',
    ],
    secondary_metrics=[
        'pe_ratio',
        'free_cash_flow',
        'gross_margin',
        'net_income',
    ],
    hidden_metrics=[
        'peg_ratio',  # Buffett doesn't care about PEG
        'institutional_ownership',  # Lynch metric
    ],

    # Buffett uses a simpler approach - just weighted scoring
    supported_algorithms=['weighted'],
    default_algorithm='weighted',
)

# Register on import
register_character(BUFFETT)
