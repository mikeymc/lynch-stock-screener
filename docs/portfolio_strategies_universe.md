# Portfolio Settings Universe & Strategy Archetypes

This document outlines the primary "dials" and "grades" available for autonomous investment strategies within the Lynch Stock Screener ecosystem. By combining these variables, we can create a vast universe of unique autonomous agents managing capital.

## Strategy Variable Categories

### 1. Investment Universe (Filters)
Defines *what* the strategy looks for in the market.

**Exposed Variables:**
- `pe_min` / `pe_max`: Trailing P/E ratio limits.
- `forward_pe_min` / `forward_pe_max`: Forward-looking valuation limits.
- `peg_min` / `peg_max`: Price/Earnings to Growth ratio.
- `market_cap_min` / `market_cap_max`: Size-based filtering (in billions).
- `dividend_yield_min`: Pure income play threshold.
- `revenue_growth_min`: Minimum YoY revenue expansion.
- `eps_growth_min`: Minimum YoY earnings expansion.
- `debt_to_equity_max`: Leverage constraints.
- `profit_margin_min`: Operational efficiency floor.
- `short_interest_min`: Sentiment-based filtering.
- `analyst_rating_min`: Consensus sentiment (1.0 = Strong Buy).
- `analyst_upside_min`: Minimum distance to mean price target.
- `revisions_up_min` / `revisions_down_min`: Earnings revision momentum.
- `sector`: Specific industry focus (e.g., 'Technology', 'Healthcare').
- `has_transcript`: Requires recent earnings call transcript availability.
- `has_fcf`: Requires Free Cash Flow data availability.
- `has_recent_insider_activity`: Requires insider buying in last 90 days.
- `top_n_by_market_cap`: Universe universe limit (e.g., "Top 500").

---

### 2. Portfolio Mechanics (Sizing & Limits)
Defines *how much* exposure the strategy takes and total portfolio capacity.

**Exposed Variables:**
- `position_sizing_method`: 
    - `equal_weight`: All picks get same $ allocation.
    - `conviction_weighted`: Scales based on Lynch/Buffett scores.
    - `fixed_pct`: Every buy is exactly X% of total value.
    - `kelly`: Uses Kelly Criterion for mathematically optimized sizing.
- `max_positions`: Hard cap on total simultaneous holdings.
- `max_position_pct`: Safety cap to prevent single-stock concentration.
- `fixed_position_pct`: Used only with `fixed_pct` method.
- `kelly_fraction`: Safety "padding" for Kelly sizing (default 0.25).
- `min_trade_amount`: Minimum $ move required to trigger a trade.
- `initial_cash`: The starting balance for new strategies.

---

### 3. Consensus & Scoring (The "Brains")
Defines the *confidence threshold* required for trade execution.

**Exposed Variables:**
- `consensus_mode`:
    - `both_agree`: Requires acceptable scores from both Lynch and Buffett.
    - `weighted_confidence`: A combined weighted average score.
    - `veto_power`: Either model can block a trade based on a floor score.
- `consensus_threshold`: The minimum score (0-100) required to initiate a trade.

---

### 4. Exit Strategy (Risk Management)
Defines *when* to autonomously liquidate a position.

**Exposed Variables:**
- `profit_target_pct`: Automatic "take profit" at X% gain.
- `stop_loss_pct`: Automatic "stop loss" at X% loss.
- `max_hold_days`: Mandatory liquidation after a time-based duration.
- `score_degradation`:
    - `lynch_below`: Exit if Lynch score falls below logic.
    - `buffett_below`: Exit if Buffett score falls below logic.

---

## The "Hidden" Universe: Unexposed Variables & Heuristics

Beyond the exposed UI toggles, the strategy engine contains several "hidden" variables—heuristics and hardcoded constants that influence behavior but are not currently adjustable in the Strategy Wizard.

### 1. Tiered Addition Thresholds (`addition_scoring_requirements`) [EXPOSED]
The system applies higher scoring requirements for symbols that are already held in the portfolio. Prevents rebalancing into declining stocks.

### 1. Hidden Heuristics & Multipliers
These variables exist in the backend code but are not mapped to UI inputs.

| Variable | Description | Default / Source |
| :--- | :--- | :--- |
| `min_trade_amount` | Minimum dollar value to trigger a trade signal. (UI currently sends `min_position_value`). | **$100.0** |
| `thesis_verdict_required` | Required AI deliberation verdicts to proceed with a BUY. | **['BUY']** |
| `universe_compliance` | Mandatory exit if a held stock no longer passes the entry universe filters. | **Always ON** |
| `kelly_fraction` | Conservative multiplier for Kelly sizing. | **0.25** |

### 2. Hardcoded Scoring Weights
The "Brains" of the characters have internal thresholds that are currently fixed.

**Warren Buffett's Weights:**
*   **ROE (40%)**: Excellent > 20%, Good > 15%, Fair > 10%.
*   **Earnings Consistency (30%)**: Scores stability of historical growth.
*   **Debt to Earnings (20%)**: Excellent < 2x, Good < 4x, Fair < 7x.
*   **Gross Margin (10%)**: Excellent > 50%, Good > 40%, Fair > 30%.

**Peter Lynch's Thresholds:**
*   **PEG Ratio**: Excellent < 1.0, Good < 1.5, Fair < 2.0.
*   **Debt to Equity**: Excellent < 0.5, Good < 1.0, Moderate < 2.0.
*   **Institutional Ownership**: "Sweet spot" between 20% and 60%.
*   **Revenue/Income Growth**: Excellent > 15%, Good > 10%, Fair > 5%.

### 3. Unexposed Stock Metrics
These data points are available in the database and can be used by the Agent via chat/tools, but are not in the Strategy Wizard's "Add Filter" dropdown:

*   **Risk**: `beta`, `analyst_count`.
*   **Ownership**: `institutional_ownership`, `insider_net_buying_6m`.
*   **Sentiment**: `short_ratio`, `short_percent_float`.
*   **Price Targets**: `price_target_high`, `price_target_low`, `price_target_mean`.
*   **Margins**: `gross_margin`, `effective_tax_rate`, `interest_expense`.

---

## Strategy Grade Examples

| Grade | Universe Focus | Mechanics | Consensus | Exit Logic |
| :--- | :--- | :--- | :--- | :--- |
| **Conservative** | Large Cap, Low Debt | 10 Picks, Fixed 5% | Both Agree >80 | Stop Loss -10% |
| **Balanced** | PEG < 1.0, GARP | 25 Picks, Equal | Combined >70 | Time Limit 180d |
| **Aggressive** | Micro Cap Growth | 50 Picks, Kelly | Combined >60 | Score Degradation |

## The Combinatorial Universe

By selecting just one primary setting from each of these four categories, we derive **81 high-level "archetype" strategies** (calculated as 3^4 = 81).

When factoring in the infinite gradients for individual variables (e.g., `pe_max` of 15.0 vs 15.1), the number of unique autonomous strategies we can deploy is effectively infinite.
