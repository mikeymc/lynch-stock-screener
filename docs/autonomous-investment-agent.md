# Autonomous Investment Agent System

## Overview

This document describes the autonomous investment agent system built for the Lynch Stock Screener. The system enables users to define investment strategies that execute autonomously in dedicated paper trading portfolios, making buy/sell decisions using the existing analysis pipeline (Lynch scoring, Buffett scoring, thesis generation, DCF analysis) and tracking performance against the S&P 500 benchmark.

### User Examples That Drove the Design

1. "Find beaten-down stocks, if Buffett thinks it's a buy, execute it"
2. "Screen for best Lynch scores, run thesis, debate with Buffett, buy if convinced"
3. "Do whatever you want - beat the S&P 500"

### Key Capabilities

- **Autonomous Execution**: Strategies run daily at market open (9:30 AM ET) without human intervention
- **Configurable Consensus**: Three modes for combining Lynch and Buffett opinions
- **Paper Trading**: All trades execute in isolated paper portfolios (real broker integration planned for later)
- **Performance Tracking**: Alpha calculation vs S&P 500 benchmark
- **Exit Management**: Automatic sell decisions based on profit targets, stop losses, and score degradation

---

## Architecture

### High-Level Flow

```
Strategy Definition (DB)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    DAILY EXECUTION FLOW                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. SCREEN          → Filter universe by conditions          │
│         │              (price drop, market cap, sector)      │
│         ▼                                                    │
│  2. SCORE           → Lynch + Buffett character scoring      │
│         │              (via lynch_criteria.evaluate_stock)   │
│         ▼                                                    │
│  3. ENRICH          → Thesis generation                      │
│         │              (via stock_analyst.get_or_generate)   │
│         ▼                                                    │
│  4. DELIBERATE      → Apply consensus mode + thesis filter   │
│         │              (both_agree / weighted / veto_power)  │
│         ▼                                                    │
│  5. CHECK EXITS     → Evaluate existing positions            │
│         │              (profit target, stop loss, score deg) │
│         ▼                                                    │
│  6. SIZE & EXECUTE  → Position sizing + paper trade          │
│         │              (via portfolio_service.execute_trade) │
│         ▼                                                    │
│  7. AUDIT           → Log decisions + track vs SPY           │
│                                                              │
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
│  │ ConditionEvaluator│  │  ConsensusEngine │  │ PositionSizer │  │
│  │                  │  │                  │  │               │  │
│  │ - evaluate_universe│ │ - both_agree    │  │ - equal_weight│  │
│  │ - _apply_filter  │  │ - weighted_conf  │  │ - conviction  │  │
│  │                  │  │ - veto_power     │  │ - fixed_pct   │  │
│  └──────────────────┘  └──────────────────┘  │ - kelly       │  │
│                                              └───────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ExitConditionChecker│ │ BenchmarkTracker │                     │
│  │                  │  │                  │                     │
│  │ - check_exits    │  │ - record_daily   │                     │
│  │ - profit_target  │  │ - record_perf    │                     │
│  │ - stop_loss      │  │ - get_series     │                     │
│  │ - score_degrade  │  └──────────────────┘                     │
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
  "require_thesis": true,
  "thesis_verdict_required": ["BUY"]
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

## Code Changes

### New Files

#### backend/strategy_executor.py (~1100 lines)
Main orchestrator containing:

1. **Data Classes**
   - `ConsensusResult`: Verdict, score, reasoning, contribution flags
   - `PositionSize`: Shares, value, position %, reasoning
   - `ExitSignal`: Symbol, quantity, reason, current value, gain %

2. **ConditionEvaluator**
   - `evaluate_universe()`: Apply filters to get candidate symbols
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
   - `_deliberate()`: Apply consensus + thesis verdict filtering
   - `_execute_trades()`: Execute buys and sells
   - `_get_current_scores()`: Helper for exit checker scoring function

### Modified Files

#### backend/database.py
Added ~20 CRUD methods:

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

**TestConditionEvaluator (2 tests):**
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

To manually trigger strategy execution:

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

| File | Purpose |
|------|---------|
| `backend/strategy_executor.py` | Main orchestrator and all components |
| `backend/database.py` | CRUD methods for strategy tables |
| `backend/worker.py` | Background job execution |
| `.github/workflows/scheduled-jobs.yml` | Scheduled job triggers |
| `tests/backend/test_strategy_executor.py` | Unit and integration tests |
| `docs/autonomous-investment-agent.md` | This documentation |

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

*Last updated: January 2026*
*Author: Claude (Opus 4.5) with Mikey*
