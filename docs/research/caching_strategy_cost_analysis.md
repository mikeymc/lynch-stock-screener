# LLM Caching Strategy & Cost Analysis

## Current State Analysis

We identified 7 key features requiring LLM processing. Below is the current model usage and estimated token load per stock.

| Feature | Current Model | Frequency | Est. Input Tokens | Est. Output Tokens | Notes |
|---------|---------------|-----------|-------------------|--------------------|-------|
| 1. Brief | gemini-2.5-flash | On-demand | ~120k (Raw) / 10k (Summary) | ~3k | Currently uses raw SEC text? |
| 2. Chart Analysis | gemini-2.5-flash | On-demand | ~15k | ~2k | Unified analysis of 3 charts |
| 3. Chat | gemini-2.5-flash | Interactive | Variable | Variable | Not pre-fetchable |
| 4. DCF Optimization | gemini-2.5-flash (Proposed) | On-demand | ~5k | ~1k | Switch to Flash for cost |
| 5. 10-K/Q Summaries | gemini-2.5-flash | Quarterly | ~80k (4 sections * 20k) | ~2k | Basis for other inputs |
| 6. 8-K Summaries | gemini-2.5-flash | Event-driven | ~10k | ~0.5k | Irregular frequency |
| 7. Earnings Transcript | gemini-2.5-flash | Quarterly | ~30k | ~1.5k | Full transcript processing |

**Pricing Assumptions:**
- **Flash (2.5)**: $0.15 / 1M Input, $0.60 / 1M Output
- **Pro (3.0)**: $2.00 / 1M Input, $12.00 / 1M Output

---

## Strategy Options

### Option A: Cache "Everything" for All 5000 Stocks
*Goal: Zero-wait state for any stock.*

**Total Stocks**: 5,000

**One-Time Initialization (Backfill)**:
1.  **Transcript Summaries**: 5000 * ($0.005) ≈ $25
2.  **10-K/Q Summaries**: 5000 * ($0.012) ≈ $60
3.  **Briefs**: 5000 * ($0.018 for Flash) ≈ $90
4.  **Chart Analysis**: 5000 * ($0.003) ≈ $15
5.  **DCF (Flash)**: 5000 * ($0.0015) ≈ $7.50
**Total Init Cost**: ~$200

**Recurring Monthly Costs (Amortized Quarterly Updates)**:
- **Monthly**: ~$66/mo (Total Init / 3 months).

### Option B: Tiered Caching (Excellent/Good Focus)
*Goal: Instant load for high-traffic "Good" stocks, on-demand for "Junk".*

**Target Stocks**: ~1,000 (Top 20%)

**Recurring Monthly Costs**:
- **~1,000 stocks**: ~20% of Option A.
- **Cost**: ~$13/mo.
- **User Experience**: Excellent stocks load instantly. Others take ~30s.

### Option C: Hybrid / On-Event
- Pre-fetch **Summaries** (Transcript, 10-K) for **ALL** stocks (Cheap: ~$28/mo).
    - This makes on-demand Brief generation much faster (inputs are ready).
- Pre-fetch **Briefs/Charts/DCF** only for **Top 1000** (Cost: ~$4/mo).
- **Total Monthly**: ~$30 - $35/mo.

---

## Recommendations

1.  **Use Flash for DCF**: Switching DCF to `gemini-2.5-flash` reduces cost from $0.02 to $0.0015 per run (-92%).
2.  **Pre-compute Summaries for All**: Caching "Building Blocks" is cheap (~$28/mo) and speeds up on-demand generation for non-cached stocks.
3.  **Full Cache for Top 1000**: Pre-generate Briefs/Charts/DCF for best stocks.
4.  **Update Triggers**:
    - **Quarterly**: Re-run the day after earnings are due (or released).
    - **8-K/News**: Re-run Brief only if **Materiality Score > 7/10**.
        - *Calculation*: A cheap Flash call analyzes the event headline/type. If deemed "High Impact" (M&A, Bankruptcy, CEO departure), trigger full re-brief.
    - **Price**: Inject live price in UI; do not re-run analysis solely for price action.

## Estimated Monthly Bill (Conservative)
*Conservative Estimate = Assuming active updates and 100% successful runs.*

- **Base Maintenance (Summaries for 5000)**: ~$30
- **Top 1000 Full Cache (Briefs/Charts/DCF)**: ~$5
- **On-Demand Usage (Users exploring tail)**: ~$10-20
- **Total**: **~$45 - $60 / month**

This is highly affordable and provides a premium experience for the majority of user traffic.
