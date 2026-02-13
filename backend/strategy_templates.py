# ABOUTME: Shared strategy template definitions for wizard UI and conversational agent
# ABOUTME: Single source of truth for filter templates, defaults, and strategy presets

FILTER_TEMPLATES = {
    "beaten_down_large_caps": {
        "name": "Beaten Down Large Caps",
        "description": "Large cap companies down 20%+ from their 52-week highs. Good for contrarian value investing.",
        "use_case": "Find large established companies that have been unfairly beaten down",
        "filters": [
            {"field": "price_vs_52wk_high", "operator": "<=", "value": -20},
            {"field": "market_cap", "operator": ">=", "value": 10000000000}
        ]
    },
    "value_stocks": {
        "name": "Value Stocks",
        "description": "Traditional value stocks with low P/E and PEG ratios. Favors mature, profitable companies.",
        "use_case": "Traditional value investing approach",
        "filters": [
            {"field": "pe_ratio", "operator": "<=", "value": 15},
            {"field": "peg_ratio", "operator": "<=", "value": 1.0}
        ]
    },
    "growth_at_reasonable_price": {
        "name": "Growth at Reasonable Price (GARP)",
        "description": "GARP strategy: PEG < 1 indicates growth trading below its rate. Peter Lynch's preferred approach.",
        "use_case": "Growth stocks at reasonable valuations",
        "filters": [
            {"field": "peg_ratio", "operator": "<=", "value": 1.0},
            {"field": "pe_ratio", "operator": ">=", "value": 5},
            {"field": "pe_ratio", "operator": "<=", "value": 30}
        ]
    },
    "low_debt_stable": {
        "name": "Low Debt, Stable Companies",
        "description": "Conservative companies with low leverage. Safer during economic downturns.",
        "use_case": "Conservative investing with lower risk",
        "filters": [
            {"field": "debt_to_equity", "operator": "<=", "value": 0.5},
            {"field": "market_cap", "operator": ">=", "value": 2000000000}
        ]
    },
    "small_cap_growth": {
        "name": "Small Cap Growth",
        "description": "Small cap companies ($300M-$2B) with growth characteristics. Higher risk, higher potential reward.",
        "use_case": "Higher risk/reward with smaller companies",
        "filters": [
            {"field": "market_cap", "operator": ">=", "value": 300000000},
            {"field": "market_cap", "operator": "<=", "value": 2000000000},
            {"field": "pe_ratio", "operator": ">=", "value": 10},
            {"field": "pe_ratio", "operator": "<=", "value": 40}
        ]
    },
    "dividend_value": {
        "name": "Dividend Value Plays",
        "description": "Value-oriented companies likely to pay dividends. Low P/E, larger market caps.",
        "use_case": "Income-focused value investing",
        "filters": [
            {"field": "pe_ratio", "operator": "<=", "value": 15},
            {"field": "market_cap", "operator": ">=", "value": 5000000000},
            {"field": "debt_to_equity", "operator": "<=", "value": 1.0}
        ]
    }
}

STRATEGY_DEFAULTS = {
    "position_sizing": {
        "method": "equal_weight",
        "max_position_pct": 10.0,
        "max_positions": 50
    },
    "consensus_mode": "both_agree",
    "consensus_threshold": 70.0,
    "schedule_cron": "0 9 * * 1-5",
    "initial_cash": 100000.0
}

# Character-specific template recommendations
# Used by personas to suggest appropriate strategies
CHARACTER_RECOMMENDATIONS = {
    "lynch": ["growth_at_reasonable_price", "small_cap_growth"],
    "buffett": ["low_debt_stable", "value_stocks", "dividend_value"]
}
