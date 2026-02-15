# Scalar vs. Vector Scoring: Consolidation Analysis

## TL;DR

**Yes, it's feasible.** The core Lynch scoring (PEG, debt, consistency, ownership) is identical
between scalar and vector paths. The Buffett-specific scores have minor band differences, but the
vector versions are arguably better calibrated. The main work is plumbing: making `evaluate_batch`
usable for single-stock lookups and backfilling a few cosmetic fields the frontend/AI endpoints expect.

---

## What We're Comparing

| Path | Used By | Entry Point | Engine |
|------|---------|-------------|--------|
| **Scalar** | Stock detail page, AI thesis, batch eval, rescorer, backtester | `LynchCriteria.evaluate_stock()` → per-metric scoring functions | `ScoringMixin` + `EarningsAnalyzer` + `MetricCalculator` |
| **Vector** | All-stocks page, movers card, strategy executor, thesis refresher | `StockVectors.load_vectors()` → `LynchCriteria.evaluate_batch()` | `BatchScoringMixin` (vectorized numpy/pandas) |

---

## Score-by-Score Comparison

### Lynch Components (PEG, Debt, Ownership, Consistency)

| Component | Formula Match? | Status Match? | Notes |
|-----------|---------------|---------------|-------|
| PEG score | **Identical** | **Identical** | Same piecewise linear bands, same NaN→0 |
| Debt score | **Identical** | **Identical** | Same bands, NaN→100 (no debt = good) |
| Ownership score | **Identical** | **Minor diff** | Scalar: any `< min` → CLOSE. Vector: only within 5pp → CLOSE, else FAIL. Score values are same. |
| Consistency score | **Identical** | N/A | Same YoY growth formula, same penalties, same normalization |
| Overall score | **Identical** | **Identical** | Same weighted sum, same threshold bands |

**Bottom line: For Lynch character, the scores will be numerically identical.**

### Buffett Components (ROE, Debt-to-Earnings, Gross Margin)

These have real differences because the scalar path uses `StockEvaluator._score_higher/lower_is_better`
(generic 0-25-75-100 bands) while the vector path uses purpose-built vectorized scorers with
compressed bands (25-50-75-100):

| Component | Scalar bands | Vector bands | Impact |
|-----------|-------------|-------------|--------|
| ROE score | 0-25, 25-75, 75-100 | 0, 25-50, 50-75, 75-100 | Moderate — vector is more generous to mediocre ROE |
| Debt-to-earnings | 0-25 (cap 14.0), 25-75, 75-100 | 0-50 (cap 10.0), 50-75, 75-100 | Moderate — vector penalizes high debt more but has higher floor |
| Gross margin | 0-25, 25-75, 75-100 | 25-50, 50-75, 75-100 | Minor — vector gives 25 minimum instead of 0 |

**Bottom line: Some Buffett scores will shift slightly. The vector versions are more opinionated
(compressed middle bands) but arguably better calibrated. Adopt the vector versions as canonical.**

### Data Source Difference

- **Gross margin**: Scalar fetches live from yfinance via `MetricCalculator`. Vector reads from `stock_metrics` DB table. The DB value is populated by the data fetcher and may be slightly stale.
- **Recommendation**: Use the DB value (vector path). Live yfinance calls are slow and unnecessary if we're fetching data regularly.

---

## Fields the Frontend/Callers Actually Need

Checked all frontend consumers and backend callers. Here's what matters:

| Field | Scalar produces | Vector produces | Frontend uses? | Other callers use? |
|-------|----------------|----------------|----------------|-------------------|
| `overall_score` | Yes | Yes | Yes | Yes (strategy executor, rescorer) |
| `overall_status` | Yes | Yes | Yes (heavy usage) | Yes |
| `peg_score`, `debt_score`, etc. | Yes | Yes | No direct use found | Used by rescorer |
| `peg_status`, `debt_status`, etc. | Yes | Yes | No direct use found | Minimal |
| `breakdown` dict | Yes | **No** | **No** | AI thesis context only |
| `rating_label` | Yes | **No** | **No** | No |
| `algorithm` | Yes | **No** | **No** | No |
| `revenue_growth_score` | Yes | **No** | **No** | No |
| `income_growth_score` | Yes | **No** | **No** | No |
| Raw metrics (pe, peg, earnings_cagr, etc.) | Yes | Yes | Yes | Yes |

**Key finding: `breakdown`, `rating_label`, `algorithm`, and the growth scores are dead fields.**
Nothing in the frontend reads them. The AI thesis endpoints pass the full eval dict as context, but
the LLM doesn't depend on those specific keys.

---

## Proposed Approach

### Phase 1: Add a single-stock vector lookup method

Add `evaluate_single(symbol, config)` to `BatchScoringMixin` or as a new utility:

```python
def evaluate_single(self, db, symbol, config):
    """Score a single stock using the vector pipeline."""
    vectors = StockVectors(db)
    df = vectors.load_vectors()
    row = df[df['symbol'] == symbol]
    if row.empty:
        return None
    scored = self.evaluate_batch(row, config)
    return scored.iloc[0].to_dict()
```

This is the naive approach. It works but loads the entire universe just to score one stock.

### Phase 2: Optimize with caching (optional)

The `StockVectors` singleton already exists in the Flask app (`deps.stock_vectors`). We could:
1. Cache `load_vectors()` with a short TTL (e.g., 5 min)
2. For single-stock lookups, filter the cached DataFrame
3. This makes single-stock scoring nearly free after the first call

### Phase 3: Replace callers

| Caller | Current | Change to |
|--------|---------|-----------|
| `GET /api/stock/<symbol>` | `evaluate_stock()` | `evaluate_single()` |
| `POST /api/stocks/batch` | Loop of `evaluate_stock()` | `evaluate_batch()` on filtered DataFrame |
| `GET /api/cached` | Loop of `evaluate_stock()` | `evaluate_batch()` on filtered DataFrame |
| AI thesis endpoints | `evaluate_stock()` | `evaluate_single()` |
| `stock_rescorer.py` | `evaluate_stock()` | `evaluate_batch()` on full set |
| `backtester.py` | `evaluate_stock()` | Needs investigation — uses historical data |
| `strategy_executor/core.py` | `evaluate_stock()` x2 | Already uses vector path in `scoring.py`; clean up the scalar call in `core.py` |

### Phase 4: Delete scalar code

Once all callers are migrated:
- Delete `ScoringMixin` (`lynch_criteria/scoring.py`)
- Delete `evaluate_stock()` from `LynchCriteriaCore` (`lynch_criteria/core.py`)
- Delete `StockEvaluator` (`stock_evaluator.py`)
- Delete `MetricCalculator` (`metric_calculator.py`) — unless other code uses it
- Simplify `EarningsAnalyzer` — its logic is duplicated in `StockVectors._compute_growth_metrics`

---

## Risks and Concerns

1. **Performance of single-stock lookups**: Loading the full vector DataFrame for one stock is
   wasteful. Mitigated by caching `load_vectors()` on the singleton with a short TTL.

2. **Backtester**: Uses `evaluate_stock()` with potentially historical data. Need to check if the
   vector path can be adapted for backtesting or if this caller needs special handling.

3. **Buffett score changes**: Some stocks' Buffett scores will change due to the band differences.
   This is a one-time shift and the vector bands are reasonable.

4. **Test coverage**: The scalar path likely has more targeted unit tests. We'd need to verify the
   vector path's tests cover the same edge cases, or port the scalar tests.

---

## Effort Estimate

- Phase 1 (evaluate_single + caching): Small
- Phase 2 (replace callers): Medium — ~7 call sites, straightforward but needs care
- Phase 3 (delete dead code): Small — satisfying deletion
- Phase 4 (update tests): Medium — porting test coverage

Total: **Medium-sized refactor**, probably 2-3 focused sessions.

---

## Recommendation

**Do it.** The redundancy is real, the vector path is the better-engineered version, and the
differences are minor and acceptable. The `breakdown` dict and other scalar-only fields are unused.
The main risk (performance for single lookups) is easily solved with DataFrame caching.

Start with Phase 1 to prove the approach works, then migrate callers incrementally.
