# Autonomous Investment Agent System

## Overview

This document describes the autonomous investment agent system built for the Lynch Stock Screener. The system enables users to define investment strategies that execute autonomously in dedicated paper trading portfolios, making buy/sell decisions using the existing analysis pipeline (Lynch scoring, Buffett scoring, thesis generation, DCF analysis) and tracking performance against the S&P 500 benchmark.

### User Examples That Drove the Design

1. "Find beaten-down stocks, if Buffett thinks it's a buy, execute it"
2. "Screen for best Lynch scores, run thesis, debate with Buffett, buy if convinced"
3. "Do whatever you want - beat the S&P 500"

### Key Capabilities

- **Autonomous Execution**: Strategies run on custom schedules (preset or custom cron) or manually on-demand
- **Universe Filtering**: Define custom stock filters (price drops, market cap, PE ratio, sector, etc.)
- **Configurable Consensus**: Three modes for combining Lynch and Buffett opinions with adjustable thresholds
- **Scoring Requirements**: Set minimum Lynch/Buffett scores for new positions and higher bars for additions
- **Thesis Verdict Requirements**: Require specific thesis verdicts (BUY/WATCH/AVOID) from AI deliberation
- **Portfolio Re-evaluation**: Automatically exit holdings that no longer meet entry criteria (opt-in)
- **Paper Trading**: All trades execute in isolated paper portfolios with two-phase cash tracking
- **Performance Tracking**: Alpha calculation vs S&P 500 benchmark with dividend attribution
- **Exit Management**: Automatic sell decisions based on profit targets, stop losses, and score degradation
- **Preview Mode**: Test strategy configuration without executing trades
- **Manual Execution**: Trigger strategy runs on-demand via UI with background job polling

---

## Architecture

### High-Level Flow

```
Strategy Definition (DB)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                     EXECUTION FLOW                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  0. DIVIDENDS       → Process dividend payments              │
│         │              (adds to cash balance)                │
│         ▼                                                    │
│  1. SCREEN          → Filter universe by custom conditions   │
│         │              (user-defined filters on any metric)  │
│         ▼                                                    │
│  2. SCORE           → Lynch + Buffett character scoring      │
│         │              (via lynch_criteria.evaluate_stock)   │
│         │              (separate thresholds for new/additions)│
│         ▼                                                    │
│  3. GENERATE THESES → Each character creates thesis          │
│         │              (Lynch thesis + Buffett thesis)       │
│         │              (via stock_analyst.get_or_generate)   │
│         ▼                                                    │
│  4. DELIBERATE      → AI moderator evaluates both theses     │
│         │              (Gemini generates consensus verdict)  │
│         │              (require specific verdicts: BUY/WATCH)│
│         ▼                                                    │
│  5. CHECK EXITS     → Evaluate existing positions            │
│         │              (profit target, stop loss, score deg) │
│         ▼                                                    │
│  5.5 RE-EVALUATE    → Check holdings vs entry criteria       │
│         │              (opt-in: exit if no longer qualify)   │
│         ▼                                                    │
│  6. SIZE & EXECUTE  → Two-phase position sizing              │
│         │              Phase 1: Calculate all positions      │
│         │              Phase 2: Execute by priority order    │
│         │              (prevents cash overdraft)             │
│         ▼                                                    │
│  7. AUDIT           → Log decisions + track vs SPY           │
│         │              (dividend attribution included)       │
│         │                                                    │
└─────────────────────────────────────────────────────────────┘
```

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      StrategyExecutor                            │
│  (Main orchestrator - backend/strategy_executor.py)             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ UniverseFilter │  │  ConsensusEngine │  │ PositionSizer │  │
│  │                  │  │                  │  │               │  │
│  │ - filter_universe│  │ - both_agree    │  │ - equal_weight│  │
│  │ - _apply_filter  │  │ - weighted_conf  │  │ - conviction  │  │
│  │                  │  │ - veto_power     │  │ - fixed_pct   │  │
│  └──────────────────┘  └──────────────────┘  │ - kelly       │  │
│                                              └───────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ExitConditionChecker│ │HoldingReevaluator│                     │
│  │                  │  │                  │                     │
│  │ - check_exits    │  │ - check_holdings │                     │
│  │ - profit_target  │  │ - check_universe │                     │
│  │ - stop_loss      │  │ - check_scoring  │                     │
│  │ - score_degrade  │  │ - grace_period   │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                  │
│  ┌──────────────────┐                                           │
│  │ BenchmarkTracker │                                           │
│  │                  │                                           │
│  │ - record_daily   │                                           │
│  │ - record_perf    │                                           │
│  │ - get_series     │                                           │
│  └──────────────────┘                                           │
│                                                                  │
│  External Dependencies (lazy-loaded):                           │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │  LynchCriteria   │  │   StockAnalyst   │                     │
│  │                  │  │                  │                     │
│  │ - evaluate_stock │  │ - get_or_generate│                     │
│  │   (lynch/buffett)│  │   _analysis      │                     │
│  └──────────────────┘  └──────────────────┘                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### New Tables (5 total)

#### 1. investment_strategies
Stores strategy definitions created by users.

```sql
CREATE TABLE IF NOT EXISTS investment_strategies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    conditions JSONB NOT NULL,
    consensus_mode TEXT NOT NULL DEFAULT 'both_agree',
    consensus_threshold REAL DEFAULT 70.0,
    position_sizing JSONB NOT NULL DEFAULT '{"method": "equal_weight", "max_position_pct": 5.0}',
    exit_conditions JSONB DEFAULT '{}',
    schedule_cron TEXT DEFAULT '0 9 * * 1-5',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Key Fields:**
- `conditions`: JSONB containing universe filters, scoring requirements, thesis requirements
- `consensus_mode`: 'both_agree', 'weighted_confidence', or 'veto_power'
- `position_sizing`: JSONB with method and constraints
- `exit_conditions`: JSONB with profit targets, stop losses, score thresholds

#### 2. strategy_runs
Tracks each execution of a strategy.

```sql
CREATE TABLE IF NOT EXISTS strategy_runs (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL REFERENCES investment_strategies(id) ON DELETE CASCADE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'running',
    stocks_screened INTEGER DEFAULT 0,
    stocks_scored INTEGER DEFAULT 0,
    theses_generated INTEGER DEFAULT 0,
    trades_executed INTEGER DEFAULT 0,
    spy_price REAL,
    portfolio_value REAL,
    run_log JSONB DEFAULT '[]',
    error_message TEXT
);
```

#### 3. strategy_decisions
Records every stock evaluation decision (whether bought or not).

```sql
CREATE TABLE IF NOT EXISTS strategy_decisions (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES strategy_runs(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    lynch_score REAL,
    lynch_status TEXT,
    buffett_score REAL,
    buffett_status TEXT,
    consensus_score REAL,
    consensus_verdict TEXT,
    thesis_verdict TEXT,
    thesis_summary TEXT,
    thesis_full TEXT,
    dcf_fair_value REAL,
    dcf_upside_pct REAL,
    final_decision TEXT,
    decision_reasoning TEXT,
    transaction_id INTEGER REFERENCES portfolio_transactions(id),
    shares_traded INTEGER,
    trade_price REAL,
    position_value REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 4. benchmark_snapshots
Daily S&P 500 (SPY) prices for performance comparison.

```sql
CREATE TABLE IF NOT EXISTS benchmark_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL UNIQUE,
    spy_price REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 5. strategy_performance
Time series of strategy performance vs benchmark.

```sql
CREATE TABLE IF NOT EXISTS strategy_performance (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL REFERENCES investment_strategies(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    portfolio_value REAL NOT NULL,
    portfolio_return_pct REAL,
    spy_return_pct REAL,
    alpha REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(strategy_id, snapshot_date)
);
```

#### 6. thesis_refresh_queue
Tracks pending and completed thesis regenerations to manage costs and freshness.

```sql
CREATE TABLE IF NOT EXISTS thesis_refresh_queue (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    reason TEXT NOT NULL,
    priority INTEGER DEFAULT 10,
    status TEXT DEFAULT 'PENDING',
    error_message TEXT,
    attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Design Decisions

### 1. Paper Trading First
**Decision**: Start with paper trading, add real broker integration later.
**Rationale**:
- Lower risk for testing and iteration
- Existing `portfolio_service.py` already supports paper trading
- Broker integration (e.g., Alpaca, Interactive Brokers) can be added as a separate layer

### 2. Scheduled (Daily) Execution
**Decision**: Run strategies once daily at market open (9:30 AM ET).
**Rationale**:
- Matches the cadence of fundamental analysis (not high-frequency)
- Reduces API costs and compute
- Aligns with when users would review decisions
- Configurable via `schedule_cron` field for future flexibility

### 3. Structured Conditions + Natural Language
**Decision**: Use JSONB for structured conditions, NL for complex reasoning (thesis).
**Rationale**:
- Structured filters are fast and deterministic for screening
- NL thesis generation captures nuanced analysis that can't be quantified
- JSONB allows flexible schema evolution without migrations

### 4. All Three Consensus Modes
**Decision**: Implement all three modes (both_agree, weighted_confidence, veto_power).
**Rationale**:
- Different strategies have different risk tolerances
- `both_agree`: Conservative, requires both characters to recommend BUY
- `weighted_confidence`: Flexible, allows one strong opinion to outweigh a weak one
- `veto_power`: Cautious, either character can block a trade

### 5. Autonomous Exit Decisions
**Decision**: Strategy can sell positions without human intervention.
**Rationale**:
- Complete autonomy requires both entry and exit
- Profit targets and stop losses are standard risk management
- Score degradation catches fundamental deterioration

### 6. Lazy Loading of Heavy Dependencies
**Decision**: `LynchCriteria` and `StockAnalyst` are lazy-loaded via properties.
**Rationale**:
- Avoids circular imports
- Reduces initialization cost when only testing components
- Makes dependency injection easier for testing

---

## Conditions JSON Format

### Universe Filters
```json
{
  "universe": {
    "filters": [
      {"field": "price_vs_52wk_high", "operator": "<=", "value": -20},
      {"field": "market_cap", "operator": ">=", "value": 1000000000},
      {"field": "pe_ratio", "operator": "<=", "value": 25},
      {"field": "sector", "operator": "==", "value": "Technology"}
    ]
  }
}
```

**Supported Fields:**
- `price_vs_52wk_high` (maps to `price_change_52w_pct`)
- `market_cap`
- `pe_ratio`
- `peg_ratio`
- `debt_to_equity`
- `price`
- `sector`

**Supported Operators:**
- `<`, `>`, `<=`, `>=`, `==`, `!=`

### Scoring Requirements
```json
{
  "scoring_requirements": [
    {"character": "lynch", "min_score": 70},
    {"character": "buffett", "min_score": 70}
  ]
}
```

### Thesis Requirements
```json
{
  "require_thesis": true,
  "thesis_verdict_required": ["BUY"]
}
```

### Complete Example
```json
{
  "universe": {
    "filters": [
      {"field": "price_vs_52wk_high", "operator": "<=", "value": -20},
      {"field": "market_cap", "operator": ">=", "value": 1000000000}
    ]
  },
  "scoring_requirements": [
    {"character": "lynch", "min_score": 70},
    {"character": "buffett", "min_score": 70}
  ],
  "addition_scoring_requirements": [
    {"character": "lynch", "min_score": 80},
    {"character": "buffett", "min_score": 80}
  ],
  "require_thesis": true,
  "thesis_verdict_required": ["BUY"],
  "holding_reevaluation": {
    "enabled": true,
    "check_universe_filters": true,
    "check_scoring_requirements": true,
    "grace_period_days": 30
  }
}
```

---

## Position Sizing JSON Format

```json
{
  "method": "equal_weight",
  "max_position_pct": 5.0,
  "min_position_value": 500,
  "fixed_position_pct": 5.0,
  "kelly_fraction": 0.25
}
```

**Methods:**
- `equal_weight`: Divide available cash equally among all buys
- `conviction_weighted`: Higher consensus score = larger position
- `fixed_pct`: Fixed percentage of portfolio per position
- `kelly`: Simplified Kelly criterion based on conviction

**Constraints:**
- `max_position_pct`: Never exceed X% of portfolio in one stock
- `min_position_value`: Don't buy less than $X (skip if can't meet minimum)

---

## Exit Conditions JSON Format

```json
{
  "profit_target_pct": 50,
  "stop_loss_pct": -20,
  "max_hold_days": 365,
  "score_degradation": {
    "lynch_below": 40,
    "buffett_below": 40
  }
}
```

**Exit Triggers:**
- `profit_target_pct`: Sell if position is up X% (e.g., 50 = sell at +50%)
- `stop_loss_pct`: Sell if position is down X% (e.g., -20 = sell at -20%)
- `max_hold_days`: Sell after holding for X days (NOT YET IMPLEMENTED)
- `score_degradation`: Sell if Lynch/Buffett score drops below threshold

---

## Consensus Modes Explained

### 1. both_agree
Both Lynch AND Buffett must recommend BUY with score >= threshold.

```python
lynch_approves = (
    lynch.score >= min_score and
    lynch.status in ['STRONG_BUY', 'BUY']
)
buffett_approves = (
    buffett.score >= min_score and
    buffett.status in ['STRONG_BUY', 'BUY']
)
verdict = 'BUY' if (lynch_approves and buffett_approves) else 'AVOID'
```

**Use Case**: Conservative strategy that only buys when both characters agree.

### 2. weighted_confidence
Combined weighted score must exceed threshold.

```python
combined_score = (lynch.score * lynch_weight) + (buffett.score * buffett_weight)
if combined_score >= 80:
    verdict = 'BUY'
elif combined_score >= threshold:
    verdict = 'WATCH'
else:
    verdict = 'AVOID'
```

**Use Case**: Balanced strategy that weighs both opinions, allows strong conviction from one to override weak from another.

### 3. veto_power
Either character can veto if strong negative conviction.

```python
lynch_vetos = (lynch.status in veto_statuses) or (lynch.score < veto_threshold)
buffett_vetos = (buffett.status in veto_statuses) or (buffett.score < veto_threshold)

if lynch_vetos or buffett_vetos:
    verdict = 'VETO'
else:
    # No veto - use average score
    avg = (lynch.score + buffett.score) / 2
    verdict = 'BUY' if avg >= 70 else 'WATCH'
```

**Use Case**: Cautious strategy that respects strong objections from either character.

---

## Deliberation System

The deliberation system adds a third AI layer that analyzes both Lynch and Buffett theses to reach a final consensus verdict. This prevents situations where both characters individually recommend BUY but for contradictory reasons.

### How It Works

1. **Dual Thesis Generation**: Lynch and Buffett each generate independent investment theses via `stock_analyst.get_or_generate_analysis()`
2. **Deliberation**: A third AI (Gemini) reads both theses and generates a final verdict
3. **Caching**: Deliberations are cached in the `deliberations` table to reduce API costs
4. **Verdict Extraction**: BUY/WATCH/AVOID verdict is extracted via regex from deliberation text

### Implementation

```python
def _conduct_deliberation(self, symbol: str, user_id: int, lynch_thesis: str, buffett_thesis: str) -> Optional[str]:
    """
    Have a third AI deliberate between Lynch and Buffett theses.
    Returns BUY, WATCH, AVOID, or None if deliberation fails.
    """
    # Check cache first
    cached = self.db.get_deliberation(user_id=user_id, symbol=symbol)
    if cached:
        return cached['final_verdict']

    # Generate deliberation
    prompt = f"""You are an impartial investment advisor...
    [Lynch's thesis]
    {lynch_thesis}

    [Buffett's thesis]
    {buffett_thesis}

    Provide your final verdict: BUY, WATCH, or AVOID"""

    deliberation_text = gemini_client.generate(prompt)
    verdict = self._extract_thesis_verdict(deliberation_text)

    # Cache result
    self.db.save_deliberation(
        user_id=user_id,
        symbol=symbol,
        lynch_thesis=lynch_thesis,
        buffett_thesis=buffett_thesis,
        deliberation_text=deliberation_text,
        final_verdict=verdict
    )

    return verdict
```

### Database Schema

```sql
CREATE TABLE IF NOT EXISTS deliberations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    lynch_thesis TEXT NOT NULL,
    buffett_thesis TEXT NOT NULL,
    deliberation_text TEXT NOT NULL,
    final_verdict TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, symbol)
);
```

### Strategy Configuration

Strategies can require specific deliberation verdicts:

```json
{
  "require_thesis": true,
  "thesis_verdict_required": ["BUY"]
}
```

If `thesis_verdict_required` is set, the deliberation verdict must match one of the specified values for the stock to proceed to trading.

---

## Content Refresh Strategy (Caching)

To manage Gemini API costs while ensuring high-quality analysis for strategy execution, a standalone background infrastructure exists to pre-compute and cache investment theses.

### Standalone Thesis Refresher Job
A dedicated background job, `thesis_refresher` (managed in `backend/worker.py`), runs periodically to populate and process a refresh queue. This decouples content generation from the active trading window, ensuring that when a strategy executes at 9:30 AM, it has fresh analysis ready to consume.

### Global Universe Filters
To prevent wasting compute and API budget on uninvestable stocks, a global filter is applied to the refresh pipeline:
- **Price**: >= $10.00
- **Market Cap**: >= $500M
- **Exclusion**: These filters are applied to all "Quality" and "Mover" signals, but are bypassed for stocks already held in a user's **Portfolio**.

### Tiered Refresh Schedule (TTL)
The refresh frequency is tiered based on the stock's status and market events:

| Category | Reason | Max Age (TTL) | Actual Frequency |
| :--- | :--- | :--- | :--- |
| **User Portfolio** | `portfolio` | 7 Days | Weekly |
| **Excellent Quality** | `quality_excellent` | 14 Days | Bi-Weekly |
| **Good Quality** | `quality_good` | 30 Days | Monthly |
| **Upcoming Earnings** | `earnings_soon` | 1 Day | Daily (during window) |
| **Big Movers** (Drops >5%)| `big_mover` | 1 Day | Daily (until stable) |

### Refresh Queue Management
The `thesis_refresh_queue` table tracks every pending and completed refresh:
- **Prioritization**: Portfolio (100) > Earnings (50) = Movers (50) > Quality (10).
- **Pruning**: The worker automatically prunes "Big Mover" entries that no longer meet the 5% drop / $10 price threshold, keeping the queue lean.
- **Parallelization**: The refresher uses a `ThreadPoolExecutor` (typically 10 threads) to process the queue rapidly without hitting per-minute API rate limits.

---

## Code Changes

### New Files

#### backend/strategy_executor.py (~1100 lines)
Main orchestrator containing:

1. **Data Classes**
   - `ConsensusResult`: Verdict, score, reasoning, contribution flags
   - `PositionSize`: Shares, value, position %, reasoning
   - `ExitSignal`: Symbol, quantity, reason, current value, gain %

2. **UniverseFilter**
   - `filter_universe()`: Apply filters to get candidate symbols
   - `_apply_filter()`: Execute single filter as SQL query

3. **ConsensusEngine**
   - `evaluate()`: Dispatch to appropriate consensus method
   - `both_agree()`: Both must approve
   - `weighted_confidence()`: Weighted average
   - `veto_power()`: Either can veto

4. **PositionSizer**
   - `calculate_position()`: Main entry point
   - `_size_equal_weight()`: Divide equally
   - `_size_conviction_weighted()`: Weight by score
   - `_size_fixed_pct()`: Fixed percentage
   - `_size_kelly()`: Kelly criterion

5. **ExitConditionChecker**
   - `check_exits()`: Check all holdings
   - `_check_holding()`: Check single holding
   - `_check_score_degradation()`: Re-score and compare

6. **BenchmarkTracker**
   - `record_daily_benchmark()`: Fetch and save SPY price
   - `record_strategy_performance()`: Calculate alpha
   - `get_performance_series()`: For charting

7. **StrategyExecutor**
   - `execute_strategy()`: Main entry point
   - `_score_candidates()`: Score with Lynch/Buffett via `lynch_criteria.evaluate_stock()`
   - `_generate_theses()`: Generate thesis via `stock_analyst.get_or_generate_analysis()`
   - `_extract_thesis_verdict()`: Parse BUY/WATCH/AVOID from thesis text
   - `_conduct_deliberation()`: Generate AI deliberation between Lynch/Buffett theses
   - `_deliberate()`: Apply consensus + thesis verdict filtering
   - `_execute_trades()`: Execute buys and sells with detailed logging
   - `_get_current_scores()`: Helper for exit checker scoring function

**Recent Enhancements to `_execute_trades()` (lines 1399-1443):**

Added comprehensive logging to diagnose trade execution issues:

```python
# Log position sizing decision
print(f"  Position sizing for {symbol}:")
print(f"    Shares: {position.shares}")
print(f"    Value: ${position.estimated_value:,.2f}")
print(f"    Reasoning: {position.reasoning}")

if position.shares > 0:
    result = portfolio_service.execute_trade(...)
    if result.get('success'):
        print(f"    ✓ Trade executed successfully")
    else:
        print(f"    ✗ Trade failed: {result.get('error', 'Unknown error')}")
else:
    print(f"    ⚠ Skipping trade: {position.reasoning}")
```

This logging reveals:
- Why position sizer returns 0 shares (e.g., "Already at max position")
- Trade execution failures (e.g., "Market is closed")
- Position sizing calculations (shares, value, reasoning)

### Modified Files

#### backend/database.py
Added ~20 CRUD methods and bug fixes:

**Strategy CRUD:**
- `create_strategy()`: Create new strategy
- `get_strategy()`: Get by ID
- `update_strategy()`: Update fields
- `delete_strategy()`: Delete strategy
- `get_enabled_strategies()`: Get all enabled strategies
- `get_user_strategies()`: Get strategies for a user

**Run Tracking:**
- `create_strategy_run()`: Create new run record
- `update_strategy_run()`: Update run with stats
- `append_to_run_log()`: Add event to run log
- `get_strategy_run()`: Get run by ID
- `get_strategy_runs()`: Get runs for a strategy

**Decision Tracking:**
- `create_strategy_decision()`: Record a decision
- `get_run_decisions()`: Get decisions for a run

**Benchmark:**
- `save_benchmark_snapshot()`: Save daily SPY price
- `get_benchmark_snapshot()`: Get snapshot by date

**Performance:**
- `save_strategy_performance()`: Save performance record
- `get_strategy_performance()`: Get performance series
- `get_strategy_inception_data()`: Get first performance record for alpha calculation

**Deliberation:**
- `save_deliberation()`: Cache deliberation result
- `get_deliberation()`: Retrieve cached deliberation

**Bug Fixes:**
- `get_portfolio_holdings()`: Fixed to return dict `{'MSFT': 10}` instead of list `[{'symbol': 'MSFT', 'net_qty': 10}]`
  - This bug caused `'list' object has no attribute 'get'` errors in PositionSizer
  - Fixed in line 3919: `return {symbol: int(qty) for symbol, qty in rows}`

#### backend/worker.py
Added strategy_execution job type:

```python
def _run_strategy_execution(self, job_id: int, params: Dict[str, Any]):
    """Execute all enabled investment strategies."""
    from strategy_executor import StrategyExecutor

    strategies = self.db.get_enabled_strategies()
    executor = StrategyExecutor(self.db)

    results = []
    for strategy in strategies:
        try:
            result = executor.execute_strategy(strategy['id'])
            results.append({'strategy_id': strategy['id'], **result})
        except Exception as e:
            results.append({'strategy_id': strategy['id'], 'error': str(e)})

    return {'strategies_executed': len(strategies), 'results': results}
```

#### .github/workflows/scheduled-jobs.yml
Added scheduled execution:

```yaml
# Strategy execution at 9:30 AM ET (2:30 PM UTC) on weekdays
- cron: '30 14 * * 1-5'
```

And case statement mapping:
```bash
"30 14 * * 1-5") echo "type=strategy_execution" >> $GITHUB_OUTPUT ;;
```

### Test Files

#### tests/backend/test_strategy_executor.py (36 tests)

**TestConsensusEngine (16 tests):**
- Both agree mode: approve, reject Lynch, reject Buffett, require BUY status
- Weighted confidence: equal weights, BUY above 80, custom weights, AVOID below threshold
- Veto power: Lynch vetos, Buffett vetos, no veto approves, double veto
- Evaluate dispatcher: both_agree, weighted_confidence, veto_power, unknown mode

**TestPositionSizer (9 tests):**
- Equal weight: single buy, multiple buys
- Conviction weighted: high conviction gets more
- Fixed percentage: allocates correct %
- Kelly criterion: high conviction allocation
- Constraints: max position %, existing position limits, at max returns zero, minimum value

**TestExitConditionChecker (6 tests):**
- Profit target triggers exit
- Stop loss triggers exit
- No exit when within bounds
- Multiple positions checked
- Empty conditions returns no exits
- Score degradation triggers exit

**TestStrategyExecutorIntegration (3 tests):**
- Full pipeline buy decision
- Thesis verdict filtering
- Disabled strategy skipped

**TestUniverseFilter (2 tests):**
- Empty filters returns all symbols
- Price filter applied

---

## How to Use

### Creating a Strategy

Strategies are stored in the database. Currently, creation is done directly via SQL or the database API (no UI yet):

```python
from database import Database

db = Database()
strategy_id = db.create_strategy(
    user_id=1,
    portfolio_id=1,
    name="Beaten Down Value Plays",
    description="Find stocks down 20%+ that both Lynch and Buffett like",
    conditions={
        "universe": {
            "filters": [
                {"field": "price_vs_52wk_high", "operator": "<=", "value": -20},
                {"field": "market_cap", "operator": ">=", "value": 1000000000}
            ]
        },
        "scoring_requirements": [
            {"character": "lynch", "min_score": 70},
            {"character": "buffett", "min_score": 70}
        ],
        "require_thesis": True,
        "thesis_verdict_required": ["BUY"]
    },
    consensus_mode="both_agree",
    consensus_threshold=70,
    position_sizing={
        "method": "equal_weight",
        "max_position_pct": 5.0,
        "min_position_value": 500
    },
    exit_conditions={
        "profit_target_pct": 50,
        "stop_loss_pct": -20,
        "score_degradation": {
            "lynch_below": 40,
            "buffett_below": 40
        }
    },
    enabled=True
)
```

### Manual Execution

**Via UI (Recommended)**

On the Strategy Detail page, click the "Run Now" button:
- Queues a background job for execution
- Shows "Running..." status while executing
- Polls for completion every 2 seconds
- Auto-refreshes strategy details when complete
- Displays errors if job fails

**Via API**

Trigger via REST endpoint:

```bash
POST /api/strategies/:id/run
```

Response:
```json
{
  "message": "Strategy run queued",
  "job_id": 123,
  "strategy_id": 1
}
```

Then poll for job status:
```bash
GET /api/jobs/123
```

**Via Python Script**

Direct execution (bypasses background queue):

```python
from database import Database
from strategy_executor import StrategyExecutor

db = Database()
executor = StrategyExecutor(db)

# Execute a specific strategy
result = executor.execute_strategy(strategy_id=1)
print(result)
# {
#     'status': 'completed',
#     'run_id': 42,
#     'stocks_screened': 150,
#     'stocks_scored': 25,
#     'theses_generated': 25,
#     'trades_executed': 3,
#     'alpha': 2.5
# }
```

### Via GitHub Actions

Trigger manually via workflow_dispatch:

1. Go to Actions → Scheduled Jobs
2. Click "Run workflow"
3. Select `strategy_execution` from dropdown
4. Click "Run workflow"

Or wait for the scheduled run at 9:30 AM ET on weekdays.

### Via API

```bash
curl -X POST "https://your-api.com/api/jobs" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"type": "strategy_execution", "params": {}}'
```

---

## How to Test

### Unit Tests

```bash
# Run all strategy executor tests
uv run pytest tests/backend/test_strategy_executor.py -v

# Run specific test class
uv run pytest tests/backend/test_strategy_executor.py::TestConsensusEngine -v

# Run with coverage
uv run pytest tests/backend/test_strategy_executor.py --cov=backend/strategy_executor
```

### Integration Test with Real Data

```python
# In a Python shell with database access
from database import Database
from strategy_executor import StrategyExecutor

db = Database()

# Create a test strategy (or use existing)
strategy_id = db.create_strategy(
    user_id=1,
    portfolio_id=1,  # Use a test portfolio
    name="Test Strategy",
    conditions={"universe": {"filters": []}},  # No filters = all stocks
    consensus_mode="weighted_confidence",
    position_sizing={"method": "fixed_pct", "fixed_position_pct": 1, "max_position_pct": 1},
    exit_conditions={},
    enabled=True
)

# Execute
executor = StrategyExecutor(db)
result = executor.execute_strategy(strategy_id)
print(result)

# Check decisions
decisions = db.get_run_decisions(result['run_id'])
for d in decisions:
    print(f"{d['symbol']}: {d['final_decision']} - {d['decision_reasoning']}")

# Clean up
db.delete_strategy(strategy_id)
```

### Verifying the Pipeline

1. **Check screening**: Look at `stocks_screened` count
2. **Check scoring**: Look at `stocks_scored` count and individual decisions
3. **Check thesis**: Look at `thesis_verdict` and `thesis_summary` in decisions
4. **Check consensus**: Look at `consensus_verdict` and `consensus_score`
5. **Check trades**: Look at portfolio transactions

```python
# Get detailed run info
run = db.get_strategy_run(run_id)
print(f"Screened: {run['stocks_screened']}")
print(f"Scored: {run['stocks_scored']}")
print(f"Theses: {run['theses_generated']}")
print(f"Trades: {run['trades_executed']}")

# Get run log
import json
for event in json.loads(run['run_log']):
    print(f"{event['timestamp']}: {event['message']}")
```

---

## Production Deployment

### Strategy 9: MSFT Autonomous Monitor

The first production strategy is configured to monitor MSFT daily:

**Configuration:**
- **Strategy ID**: 9
- **Name**: "Autonomous MSFT Monitor"
- **Portfolio**: Portfolio 1 ("Lynch") with ~$64,000 cash
- **Universe Filter**: `symbol == "MSFT"`
- **Scoring Requirements**: Lynch ≥ 70, Buffett ≥ 70
- **Thesis Requirements**: Requires theses from BOTH characters
- **Deliberation**: Uses Gemini AI to deliberate between Lynch/Buffett theses
- **Consensus Mode**: `both_agree` (both must recommend BUY)
- **Position Sizing**: `fixed_pct` at 10% of portfolio per position
- **Schedule**: Daily at 9:30 AM ET (via GitHub Actions cron)
- **Status**: `enabled=True`

**SQL to Create Strategy 9:**

```sql
INSERT INTO investment_strategies (
    user_id, portfolio_id, name, description,
    conditions, consensus_mode, consensus_threshold,
    position_sizing, exit_conditions, schedule_cron, enabled
) VALUES (
    1,
    1,
    'Autonomous MSFT Monitor',
    'Daily autonomous monitoring of MSFT. Requires Lynch and Buffett both score 70+, generates theses with deliberation, executes 10% position on BUY consensus.',
    '{
      "universe": {
        "filters": [
          {"field": "symbol", "operator": "==", "value": "MSFT"}
        ]
      },
      "scoring_requirements": [
        {"character": "lynch", "min_score": 70},
        {"character": "buffett", "min_score": 70}
      ],
      "require_thesis": true,
      "thesis_verdict_required": ["BUY"]
    }'::jsonb,
    'both_agree',
    70.0,
    '{
      "method": "fixed_pct",
      "max_position_pct": 10.0,
      "fixed_position_pct": 10.0
    }'::jsonb,
    '{
      "profit_target_pct": 50,
      "stop_loss_pct": -20
    }'::jsonb,
    '30 9 * * 1-5',
    true
) RETURNING id;
```

### GitHub Actions Integration

The strategy executes automatically via GitHub Actions cron job:

```yaml
# .github/workflows/scheduled-jobs.yml
- cron: '30 14 * * 1-5'  # 9:30 AM ET = 2:30 PM UTC on weekdays
```

The workflow calls the API to create a `strategy_execution` background job, which is processed by `worker.py`:

```python
# backend/worker.py (lines 233-234)
elif job_type == 'strategy_execution':
    self._run_strategy_execution(job_id, params)
```

### Helper Scripts

Several helper scripts were created for testing and maintenance:

#### cleanup_strategies.py
Disables duplicate/test strategies:

```python
from database import Database

db = Database()

# Disable test strategies 1-4, keep only 9
for strategy_id in [1, 2, 3, 4]:
    db.update_strategy(strategy_id=strategy_id, user_id=1, enabled=False)

# Verify only strategy 9 is enabled
enabled = db.get_enabled_strategies()
assert len(enabled) == 1 and enabled[0]['id'] == 9
```

#### verify_autonomous_strategy.py
Comprehensive status check showing:
- Strategy configuration
- Portfolio state (total value, cash, holdings)
- Recent execution history
- Data cache status (metrics, theses, deliberations)

```bash
uv run python backend/verify_autonomous_strategy.py
```

#### run_strategy_9.py
Simple local testing script:

```python
from database import Database
from strategy_executor import StrategyExecutor

db = Database()
executor = StrategyExecutor(db)

# Show portfolio before
portfolio = db.get_portfolio_summary(1, use_live_prices=False)
print(f"Cash: ${portfolio['cash']:,.2f}")

# Execute strategy
result = executor.execute_strategy(9)
print(f"Status: {result['status']}")
print(f"Trades: {result['trades_executed']}")

# Show portfolio after
portfolio = db.get_portfolio_summary(1, use_live_prices=False)
print(f"Cash: ${portfolio['cash']:,.2f}")
```

#### update_strategy_position_size.py
Updates position sizing parameters:

```python
from database import Database

db = Database()

# Increase max_position_pct from 1% to 10%
strategy = db.get_strategy(9)
position_sizing = strategy['position_sizing']
position_sizing['max_position_pct'] = 10.0
position_sizing['fixed_position_pct'] = 10.0

db.update_strategy(
    strategy_id=9,
    user_id=1,
    position_sizing=position_sizing
)
```

### Common Production Issues and Fixes

#### Issue 1: `'list' object has no attribute 'get'`
**Symptom**: Position sizer crashes when checking existing holdings

**Root Cause**: `get_portfolio_holdings()` returned list of dicts instead of dict

**Fix**: Updated database.py line 3919:
```python
# Before (buggy):
return [dict(zip(columns, row)) for row in cursor.fetchall()]

# After (fixed):
return {symbol: int(qty) for symbol, qty in rows}
```

#### Issue 2: BUY decision executes 0 trades
**Symptom**: Deliberation returns BUY verdict but no trades execute

**Possible Causes**:
1. **Market closed**: Trades only execute 4 AM - 8 PM ET on weekdays
2. **Position limit reached**: Already at `max_position_pct` for that stock
3. **Insufficient cash**: Not enough cash to meet `min_position_value`

**Diagnosis**: Check the detailed logging output from `_execute_trades()`:
```
Position sizing for MSFT:
  Shares: 0
  Value: $0.00
  Reasoning: Already at max position (10 shares = $4236.75)
  ⚠ Skipping trade: Already at max position
```

**Fix**: Either increase `max_position_pct` or sell existing position first

#### Issue 3: Deliberation verdict is None
**Symptom**: Thesis generated successfully but deliberation returns None

**Possible Causes**:
1. **Gemini API error**: 503, 404, or rate limit
2. **Verdict extraction failed**: Deliberation text generated but parsing failed
3. **Missing API key**: `GOOGLE_API_KEY` not set in environment

**Diagnosis**: Check strategy_runs.run_log for error messages

**Fix**: Verify API key, check retry logic, ensure deliberation prompt requests verdict in expected format

#### Issue 4: Unknown job type: strategy_execution
**Symptom**: GitHub Actions cron creates job but worker doesn't process it

**Root Cause**: Production deployment missing latest worker.py code

**Fix**: Deploy worker.py with `strategy_execution` handler (lines 233-234)

---

## Known Limitations and Future Work

### Not Yet Implemented

1. **max_hold_days exit condition**: Would require tracking purchase dates per position
2. **REST API endpoints**: Strategy CRUD via API (currently DB-only)
3. **Strategy Builder UI**: Frontend for creating/editing strategies
4. **Performance Dashboard**: Charts showing strategy performance vs SPY
5. **Real Broker Integration**: Connect to Alpaca, Interactive Brokers, etc.
6. **Multi-region support**: Currently US stocks only

### Edge Cases to Consider

1. **Empty universe after filtering**: Currently returns empty list, strategy proceeds with 0 candidates
2. **API rate limits**: Thesis generation and scoring hit external APIs, may need throttling
3. **Market hours**: Strategy runs at 9:30 AM ET but doesn't check if market is open (holidays)
4. **Partial failures**: If thesis generation fails for one stock, it continues with others
5. **Duplicate buys**: If already holding a stock, position sizer limits additional purchase
6. **Cash insufficiency**: If not enough cash for minimum position, stock is skipped

### Potential Improvements

1. **Caching**: Cache scores and theses to avoid regenerating on subsequent runs
2. **Backtesting**: Run strategy against historical data to evaluate performance
3. **Notifications**: Alert user when trades are executed or exit conditions triggered
4. **Strategy templates**: Pre-built strategies users can clone and modify
5. **Sector/industry constraints**: Diversification rules (max % in one sector)
6. **Correlation analysis**: Avoid buying highly correlated stocks

---

## File Reference

### Core Implementation Files

| File | Purpose | Lines |
|------|---------|-------|
| `backend/strategy_executor.py` | Main orchestrator and all components | ~1500 |
| `backend/database.py` | CRUD methods for strategy tables + deliberations | ~4000 |
| `backend/worker.py` | Background job execution (strategy_execution handler) | ~500 |
| `.github/workflows/scheduled-jobs.yml` | Scheduled job triggers (9:30 AM ET cron) | ~200 |
| `tests/backend/test_strategy_executor.py` | Unit and integration tests (36 tests) | ~1000 |
| `docs/autonomous-investment-agent.md` | This documentation | ~1000 |

### Helper Scripts

| File | Purpose |
|------|---------|
| `backend/cleanup_strategies.py` | Disable duplicate test strategies |
| `backend/verify_autonomous_strategy.py` | Comprehensive status checker for Strategy 9 |
| `backend/run_strategy_9.py` | Simple local testing script with before/after portfolio state |
| `backend/test_autonomous_strategy.py` | Detailed manual execution test (superseded by run_strategy_9.py) |
| `backend/update_strategy_position_size.py` | Update max_position_pct for existing strategy |
| `backend/investigate_run9.py` | Diagnostic script to analyze specific run failures |
| `backend/test_trade_execution_fix.py` | Test script for get_portfolio_holdings fix |

### Existing Files Used (Not Modified)

| File | Usage |
|------|-------|
| `backend/character_scoring.py` | Character-based scoring (not directly used, via lynch_criteria) |
| `backend/lynch_criteria.py` | `evaluate_stock()` for Lynch/Buffett scoring |
| `backend/stock_analyst.py` | `get_or_generate_analysis()` for thesis generation |
| `backend/portfolio_service.py` | `execute_trade()` for paper trading |
| `backend/earnings_analyzer.py` | Required by LynchCriteria |

---

## Debugging Tips

### Strategy Not Executing

1. Check if strategy is enabled: `db.get_strategy(id)['enabled']`
2. Check if portfolio exists: `db.get_portfolio_summary(portfolio_id)`
3. Check run status: `db.get_strategy_runs(strategy_id)`
4. Check error message: `run['error_message']`

### No Stocks Being Scored

1. Check universe filters are not too restrictive
2. Verify `stock_metrics` table has data
3. Check run log for "Screened X candidates" message

### No Trades Being Executed

1. Check if stocks pass scoring requirements
2. Check if thesis verdict matches required verdicts
3. Check consensus mode is producing BUY verdicts
4. Check if portfolio has sufficient cash
5. Check if max_position_pct is already reached

### Viewing Decision Details

```python
decisions = db.get_run_decisions(run_id)
for d in decisions:
    print(f"""
Symbol: {d['symbol']}
Lynch: {d['lynch_score']:.0f} ({d['lynch_status']})
Buffett: {d['buffett_score']:.0f} ({d['buffett_status']})
Consensus: {d['consensus_score']:.0f} ({d['consensus_verdict']})
Thesis: {d['thesis_verdict']}
Final: {d['final_decision']}
Reason: {d['decision_reasoning']}
""")
```

---

## Glossary

- **Alpha**: Portfolio return minus benchmark (SPY) return
- **Consensus**: Agreement between Lynch and Buffett characters
- **Conviction**: Strength of buy recommendation (higher score = more conviction)
- **Kelly Criterion**: Position sizing based on edge and probability
- **Paper Trading**: Simulated trading without real money
- **SPY**: S&P 500 ETF used as benchmark
- **Thesis**: AI-generated investment analysis with BUY/WATCH/AVOID verdict
- **Universe**: Set of stocks being considered for trading
- **Veto**: Strong negative opinion that blocks a trade

---

## Changelog

### February 2026
**Strategy Wizard Gap Closure & Critical Fixes**
- **Universe Filters**: Added full filter builder UI with field/operator/value rows
- **Scoring Requirements**: Added Lynch/Buffett minimum score sliders (0-100, step 5)
- **Thesis Verdict Requirements**: Added BUY/WATCH/AVOID verdict checkboxes
- **Score Degradation Exits**: Extended exit conditions with Lynch/Buffett score thresholds
- **Portfolio Creation**: Added custom portfolio name and initial cash amount inputs
- **Consensus Threshold**: Added conditional threshold input for weighted_confidence mode
- **Schedule Control**: Extended schedule with custom cron and manual-only options
- **Preview Mode**: Added preview button to test strategy before enabling
- **Manual Execution**: Added "Run Now" button with background job polling
- **Two-Phase Cash Tracking**: Fixed cash overflow by calculating all positions before execution
- **Dividend Tracking**: Added dividend income visibility and performance attribution
- **Portfolio Re-evaluation**: Added automatic exit for holdings that no longer meet criteria (opt-in)
- **Position Addition Control**: Higher conviction thresholds for adding to existing positions
- All 9 gaps between backend capabilities and frontend UI now closed

### January 31, 2026
- Added deliberation system (third AI layer to reconcile Lynch/Buffett theses)
- Fixed `get_portfolio_holdings()` to return dict instead of list
- Added comprehensive logging to `_execute_trades()` showing position sizing decisions
- Created helper scripts for testing and maintenance
- Configured Strategy 9 (MSFT Autonomous Monitor) for production
- Increased max_position_pct from 1% to 10% based on portfolio size
- Documented common production issues and fixes

### January 2026 (Initial Release)
- Implemented autonomous investment strategy system
- Added 6-phase execution pipeline (screen, score, thesis, deliberate, exit check, trade)
- Created 5 database tables for strategy tracking
- Implemented 3 consensus modes (both_agree, weighted_confidence, veto_power)
- Added 4 position sizing methods (equal_weight, conviction_weighted, fixed_pct, kelly)
- Integrated with GitHub Actions for scheduled execution
- Wrote 36 unit and integration tests

---

*Last updated: February 3, 2026*
*Author: Claude (Sonnet 4.5) with Mikey*
