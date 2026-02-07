# Split Files Changeset Walkthrough

## Overview

This branch splits 10 Python files that exceeded 1,000 lines of code into packages. Each original `.py` file becomes a directory containing focused modules, with an `__init__.py` that re-exports the public API so all existing imports continue working.

**Branch:** `split-files` (10 commits off `main`)

**Stats:** 112 files changed, 31,196 insertions, 30,334 deletions

**Tests:** 463 backend + 8 CLI = 471 passed, 2 skipped, 0 failed

---

## Files Split

| # | Original File | Lines | Modules | Pattern | Commit |
|---|--------------|-------|---------|---------|--------|
| 1 | `strategy_executor.py` | 2,008 | 8 | Class-per-file | `2840151` |
| 2 | `stock_analyst.py` | 1,037 | 4 | Mixin classes | `383568b` |
| 3 | `lynch_criteria.py` | 1,217 | 4 | Mixin classes | `a863c66` |
| 4 | `data_fetcher.py` | 1,297 | 4 | Mixin classes | `7ce317d` |
| 5 | `edgar_fetcher.py` | 4,759 | 10 | Mixin classes | `21df995` |
| 6 | `agent_tools.py` | 3,387 | 9 | Declarations + mixins | `bcdfce4` |
| 7 | `cli/commands/cache.py` | 1,353 | 5 | Function grouping | `95a09bb` |
| 8 | `worker.py` | 3,594 | 11 | Mixin classes | `7f29ba9` |
| 9 | `database.py` | 7,418 | 14 | Mixin classes | `6b42fd4` |
| 10 | `app.py` | 5,110 | 15 | Flask Blueprints | `85cac33` |

---

## Splitting Patterns

Three patterns were used, chosen based on each file's structure:

### Pattern A: Mixin Classes

Used for files with a single large class (database, worker, edgar_fetcher, data_fetcher, lynch_criteria, stock_analyst, agent_tools).

Methods are grouped by domain into mixin classes. The final class is assembled via multiple inheritance in `__init__.py`.

```python
# database/stocks.py
class StocksMixin:
    def save_stock_basic(self, symbol, name, ...): ...
    def get_stock_metrics(self, symbol): ...

# database/__init__.py
from database.core import DatabaseCore
from database.stocks import StocksMixin
from database.analysis import AnalysisMixin
# ... all mixins ...

class Database(DatabaseCore, StocksMixin, AnalysisMixin, ...):
    pass
```

**Why this works:** Mixins access shared state via `self`, which resolves at runtime through the composed class. Each mixin file only needs its own imports. No circular dependencies because mixins never import from the parent package.

### Pattern B: Flask Blueprints

Used for `app.py`, which had 103 route handlers plus extensive module-level setup.

Route handlers are extracted into Blueprint modules. Shared state (db, fetcher, etc.) lives in `deps.py` — a module with `None` placeholders that `__init__.py` populates at startup.

```python
# app/deps.py
db = None
fetcher = None
stock_analyst = None
# ...

# app/__init__.py
from app import deps
deps.db = Database(host=..., ...)
deps.fetcher = DataFetcher(deps.db)
# ... register blueprints ...

# app/stocks.py
from flask import Blueprint
from app import deps

stocks_bp = Blueprint('stocks', __name__)

@stocks_bp.route('/api/stock/<symbol>')
def get_stock(symbol):
    metrics = deps.db.get_stock_metrics(symbol)
    # ...
```

**Why deps.py instead of passing args:** Flask blueprints can't receive constructor arguments. Module-level state is the standard Flask pattern. `deps.py` makes the shared state explicit and patchable in tests.

### Pattern C: Class-per-file

Used for `strategy_executor.py`, which already contained multiple distinct classes (`ConditionEvaluator`, `ConsensusEngine`, `PositionSizer`, etc.).

Each class moves to its own file. `__init__.py` re-exports everything.

### Pattern D: Function grouping

Used for `cli/commands/cache.py`, which contained Typer CLI commands.

Related commands are grouped into files. Each file imports the shared Typer `app` and registers commands on it.

---

## Package-by-Package Details

### 1. `backend/strategy_executor/` (8 files, 2,065 lines)

**Original:** Single file with 7 classes + dataclasses.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 10 | Re-exports all classes |
| `models.py` | 34 | `ConsensusResult`, `PositionSize`, `ExitSignal` dataclasses |
| `conditions.py` | 99 | `ConditionEvaluator` |
| `consensus.py` | 161 | `ConsensusEngine` |
| `position_sizing.py` | 190 | `PositionSizer` |
| `exit_conditions.py` | 145 | `ExitConditionChecker` |
| `holding_reevaluation.py` | 170 | `HoldingReevaluator` |
| `executor.py` | 1,256 | `BenchmarkTracker` + `StrategyExecutor` |

**Note:** `executor.py` is 1,256 lines. `StrategyExecutor` is a single cohesive orchestration class with many private methods. Splitting it further would create artificial seams.

---

### 2. `backend/stock_analyst/` (4 files, 1,082 lines)

**Original:** `StockAnalyst` class with prompt building, analysis generation, and summary methods.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 10 | Composes `StockAnalyst` from mixins, re-exports constants |
| `core.py` | 396 | `__init__`, `client` property, prompt template methods, model constants |
| `analysis.py` | 206 | `generate_analysis_stream`, `get_or_generate_analysis` |
| `generation.py` | 470 | `generate_unified_chart_analysis`, `generate_filing_section_summary`, `generate_dcf_recommendations`, `generate_transcript_summary` |

---

### 3. `backend/lynch_criteria/` (4 files, 1,251 lines)

**Original:** `LynchCriteria` class with scoring logic and vectorized batch evaluation.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 10 | Composes `LynchCriteria`, re-exports `ALGORITHM_METADATA`, `SCORE_THRESHOLDS` |
| `core.py` | 433 | `__init__`, `evaluate_stock`, `_evaluate_weighted`, constants |
| `scoring.py` | 345 | Individual metric scoring (`calculate_peg_score`, `evaluate_debt`, etc.) |
| `batch.py` | 463 | `evaluate_batch` with vectorized numpy scoring |

---

### 4. `backend/data_fetcher/` (4 files, 1,329 lines)

**Original:** `DataFetcher` class for fetching stock data from Yahoo Finance + EDGAR.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 10 | Composes `DataFetcher`, re-exports `retry_on_rate_limit` |
| `core.py` | 547 | `__init__`, `fetch_stock_data`, yfinance helpers, `fetch_multiple_stocks` |
| `earnings.py` | 502 | `_store_edgar_earnings`, `_fetch_and_store_earnings`, quarterly earnings |
| `financials.py` | 270 | `_backfill_debt_to_equity`, `_backfill_cash_flow`, dividend fetching |

---

### 5. `backend/edgar_fetcher/` (10 files, 4,874 lines)

**Original:** `EdgarFetcher` class with SEC EDGAR API parsing for many financial metrics.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 18 | Composes `EdgarFetcher` from 8 mixins |
| `core.py` | 266 | `__init__`, rate limiting, CIK lookup, `fetch_company_facts`, `get_value` |
| `eps.py` | 428 | EPS history parsing (annual + quarterly, split-adjusted) |
| `revenue.py` | 346 | Revenue history parsing (annual + quarterly) |
| `income.py` | 326 | Net income parsing |
| `cash_flow.py` | 556 | Cash flow, cash equivalents, interest expense parsing |
| `shares.py` | 293 | Shares outstanding parsing |
| `equity_debt.py` | 700 | Shareholder equity, debt-to-equity, effective tax rate |
| `fundamentals.py` | 1,035 | `fetch_stock_fundamentals`, quarterly XBRL extraction |
| `filings.py` | 906 | Recent filings, Form 4 parsing, dividend history |

---

### 6. `backend/agent_tools/` (9 files, 3,450 lines)

**Original:** Tool declarations (data) + `ToolExecutor` class.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 17 | Composes `ToolExecutor`, re-exports `AGENT_TOOLS`, `TOOL_DECLARATIONS` |
| `declarations.py` | 710 | All `FunctionDeclaration` objects and the `TOOL_DECLARATIONS` list |
| `core.py` | 86 | `ToolExecutorCore.__init__` and `execute()` dispatch |
| `stock_tools.py` | 529 | `_get_stock_metrics`, `_get_financials`, etc. |
| `portfolio_tools.py` | 206 | `_create_portfolio`, `_buy_stock`, `_sell_stock`, etc. |
| `research_tools.py` | 496 | `_get_peers`, `_get_insider_activity`, `_search_news`, etc. |
| `analysis_tools.py` | 584 | `_get_growth_rates`, `_compare_stocks`, `_search_company`, etc. |
| `screening_tools.py` | 531 | `_get_earnings_history`, `_screen_stocks` |
| `utility_tools.py` | 291 | `_manage_alerts`, `_get_fred_series`, `_get_economic_indicators` |

---

### 7. `cli/commands/cache/` (5 files, 1,385 lines)

**Original:** Typer CLI commands for cache warming.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 12 | Creates Typer `app`, imports command modules to register commands |
| `helpers.py` | 99 | `get_api_url`, `get_api_token`, `get_headers`, `_start_cache_job`, `_stop_cache_job` |
| `data_commands.py` | 413 | `history`, `prices`, `historical`, `quarterly` commands |
| `content_commands.py` | 513 | `news`, `outlook`, `transcripts`, `forward_metrics`, `theses` commands |
| `filing_commands.py` | 348 | `ten_k`, `eight_k`, `form4`, `all_caches` commands |

---

### 8. `backend/worker/` (11 files, 3,741 lines)

**Original:** `BackgroundWorker` class with one `_run_*` method per job type.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 50 | **yfinance cache monkey-patch** (must execute first) + compose class |
| `core.py` | 220 | `__init__`, `run` loop, `_execute_job` dispatch, heartbeat, `get_memory_mb` |
| `data_jobs.py` | 630 | Historical fundamentals, quarterly, prices, dividends |
| `sec_jobs.py` | 659 | SEC refresh, 10-K cache, 8-K cache, Form 4 cache |
| `content_jobs.py` | 1,031 | News, outlook, transcript, forward metrics caching |
| `screening_jobs.py` | 207 | Stock screening |
| `thesis_jobs.py` | 408 | Thesis refresh |
| `alert_jobs.py` | 324 | Alert checking with LLM evaluation |
| `portfolio_jobs.py` | 62 | Portfolio/benchmark snapshots |
| `strategy_jobs.py` | 122 | Strategy execution |
| `main.py` | 28 | `main()` entry point |

**Special:** `worker/__init__.py` contains the yfinance cache monkey-patch (lines 1-28 from the original) which MUST execute before any yfinance imports. This is why it lives in `__init__.py` rather than a separate file.

---

### 9. `backend/database/` (14 files, 7,570 lines)

**Original:** `Database` class with 183 public methods — the largest file at 7,418 lines.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 22 | Composes `Database` from 12 mixins |
| `core.py` | 401 | `__init__`, connection pool, writer thread, `flush`, `_sanitize_numpy_types` |
| `schema.py` | 1,800 | `_init_schema_with_connection`, `_init_rest_of_schema` (DDL statements) |
| `stocks.py` | 756 | Stock CRUD, earnings, weekly prices, cache validity, search |
| `analysis.py` | 730 | Lynch analysis, chart analysis, DCF, estimates, transcripts |
| `filings.py` | 705 | SEC filings, filing sections, news, material events |
| `portfolios.py` | 649 | Portfolio CRUD, transactions, holdings, performance |
| `screening.py` | 585 | Screening sessions, results, backtest results |
| `strategies.py` | 548 | Strategy CRUD, runs, decisions, benchmarks, performance |
| `social.py` | 344 | Reddit sentiment, agent conversations/messages |
| `jobs.py` | 317 | Background job lifecycle (create, claim, heartbeat, complete) |
| `settings.py` | 303 | App settings, algorithm configs |
| `users.py` | 224 | User accounts, watchlist, preferences |
| `alerts.py` | 186 | Price/condition alert CRUD |

**Note:** `schema.py` is 1,800 lines but is pure DDL (CREATE TABLE statements). Low complexity per line and splitting it would scatter the schema definition.

---

### 10. `backend/app/` (15 files, 5,475 lines)

**Original:** Flask app with 103 route handlers plus session/CORS/service initialization.

| File | Lines | Contents |
|------|-------|----------|
| `__init__.py` | 223 | Flask app creation, middleware, session, CORS, service init, blueprint registration |
| `deps.py` | 20 | Shared dependency placeholders (`db`, `fetcher`, `stock_analyst`, etc.) |
| `helpers.py` | 50 | `clean_nan_values`, `generate_conversation_title` |
| `auth.py` | 343 | OAuth, login, registration, email verification |
| `jobs.py` | 132 | Background job creation with flexible auth (OAuth or API token) |
| `strategies.py` | 326 | Strategy CRUD, templates, manual runs |
| `settings.py` | 397 | Algorithm metadata, AI models, app settings, character/theme |
| `stocks.py` | 1,047 | Stock data, history, batch, insider trades, search, screening results |
| `analysis.py` | 717 | Thesis, chart analysis, DCF, outlook, transcripts |
| `screening.py` | 368 | Screening progress, results, start/stop |
| `filings.py` | 414 | SEC filings, sections, news, Reddit, material events |
| `portfolios.py` | 225 | Watchlist, portfolio CRUD, trades, value history |
| `agent.py` | 187 | AI agent chat (streaming + sync) |
| `backtesting.py` | 431 | Backtesting, validation, optimization |
| `dashboard.py` | 595 | FRED data, alerts, market overview, feedback |

**How shared state works:**

1. `deps.py` declares `None` placeholders for every service
2. `__init__.py` creates real instances and assigns them: `deps.db = Database(...)`, `deps.fetcher = DataFetcher(deps.db)`, etc.
3. Blueprint files import `deps` and access services: `deps.db.get_stock_metrics(symbol)`
4. For backward compatibility, `__init__.py` also exports `db = deps.db` so `from app import db` still works

---

## Test Changes

16 test files were updated. The changes fall into three categories:

### 1. Monkeypatch targets moved to `deps`

Before (patching module-level var on old `app.py`):
```python
import app as app_module
monkeypatch.setattr(app_module, 'db', test_db)
monkeypatch.setattr(app_module, 'stock_analyst', mock_analyst)
monkeypatch.setattr(app_module, 'API_AUTH_TOKEN', None)
```

After (patching the `deps` module where blueprints actually read them):
```python
import app as app_module
monkeypatch.setattr(app_module.deps, 'db', test_db)
monkeypatch.setattr(app_module.deps, 'stock_analyst', mock_analyst)
monkeypatch.setattr(app_module.deps, 'API_AUTH_TOKEN', None)
```

**Affected files:** test_app.py, test_portfolio_api.py, test_job_api.py, test_caching.py, test_caching_verbose.py, test_price_provider.py, test_backtest_api.py, test_flexible_auth.py, test_worker_data_caching.py

### 2. Patch targets for moved functions/imports

When a module moves, `@patch` decorators need to target where the name is looked up at runtime:

```python
# Before
patch('app.get_fred_service', ...)
patch('stock_analyst.genai.Client')
patch('worker.portfolio_service')

# After
patch('app.dashboard.get_fred_service', ...)
patch('stock_analyst.core.genai.Client')
patch('worker.alert_jobs.portfolio_service')
```

**Affected files:** test_app.py, test_dcf_recommendations.py, test_lynch_analyst.py, test_stock_analyst_retry.py, test_trading_alerts.py

### 3. Source file paths in test_form4_skip_logic.py

This test reads source files directly to verify SQL queries. Paths updated:
- `backend/database.py` → `backend/database/stocks.py`
- `backend/worker.py` → `backend/worker/sec_jobs.py`

---

## Bug Fix During Split

The agent-generated `check_for_api_token()` in `app/jobs.py` and `app/auth.py` had incorrect auth logic. When `API_AUTH_TOKEN` was `None` (not configured, typical for local dev), it fell through to returning 401 instead of allowing access.

**Before (incorrect):**
```python
if deps.API_AUTH_TOKEN:
    # check bearer token...
# Falls through to 401 even when no token is configured
return jsonify({'error': 'Unauthorized'}), 401
```

**After (correct):**
```python
if not deps.API_AUTH_TOKEN:
    return None  # No token configured, allow access

# check bearer token...
return jsonify({'error': 'Unauthorized'}), 401
```

---

## Remaining Files Over 1,000 Lines

| File | Lines | Why it's acceptable |
|------|-------|-------------------|
| `database/schema.py` | 1,800 | Pure DDL SQL (CREATE TABLE). Low complexity per line. |
| `strategy_executor/executor.py` | 1,256 | Single cohesive orchestration class. |
| `app/stocks.py` | 1,047 | Dense endpoint handlers, barely over threshold. |
| `edgar_fetcher/fundamentals.py` | 1,035 | Related XBRL parsing logic. |
| `worker/content_jobs.py` | 1,031 | Similar job handlers grouped together. |

---

## How to Verify

```bash
# Run all backend tests
python3 -m pytest tests/backend/ -x -v   # 463 passed, 2 skipped

# Run CLI tests
python3 -m pytest tests/cli/ -x -v       # 8 passed

# Check no imports broke
python3 -c "from database import Database; from app import app; from worker import BackgroundWorker; from edgar_fetcher import EdgarFetcher; from data_fetcher import DataFetcher; from lynch_criteria import LynchCriteria; from stock_analyst import StockAnalyst; from agent_tools import ToolExecutor, AGENT_TOOLS; from strategy_executor import StrategyExecutor; print('All imports OK')"

# Check remaining large files
find backend -name '*.py' -exec wc -l {} \; | awk '$1 >= 1000' | sort -rn
```

---

## Key Design Decisions

1. **Mixin pattern over delegation:** Mixins keep the same `self.method()` calling convention. No need to change internal method calls. The final composed class has the same interface as the original.

2. **`deps.py` for Flask shared state:** Standard Flask pattern. Explicit, patchable in tests, avoids circular imports between blueprints and `__init__.py`.

3. **No test file splits:** Test files were only modified to fix patch targets, not restructured. Splitting test files was out of scope.

4. **Backward-compatible `__init__.py` re-exports:** Every package's `__init__.py` re-exports the public API. `from database import Database` still works, `from app import app, db` still works, `from worker import BackgroundWorker` still works. No consumer code needs to know about the split.

5. **ABOUTME comments on every file:** Per project convention, every new `.py` file starts with two `# ABOUTME:` lines explaining what the file does.
