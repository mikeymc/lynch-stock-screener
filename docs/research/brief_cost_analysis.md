# Brief Generation: Cost & Strategy Analysis

## Executive Summary

The Brief page currently uses Gemini API to generate Peter Lynch-style stock analyses. Real-time generation takes **20+ seconds** due to prompt size (~464K chars with full SEC context). The solution is **overnight pre-computation** with selective regeneration.

**Recommended approach**: Pre-compute briefs for 1,000 excellent/good stocks quarterly using Gemini 3 Pro at **~$90/month**.

---

## Prompt Composition Breakdown

| Component | Size | Tokens | % of Total | Notes |
|-----------|------|--------|------------|-------|
| Base Template | ~2,200 chars | ~550 | 0.5% | Instructions + formatting |
| Lynch Checklist | ~7,900 chars | ~2,000 | 1.7% | Investment criteria |
| Stock Metrics | ~500 chars | ~125 | 0.1% | Price, P/E, PEG, D/E |
| Historical Data | ~600 chars | ~150 | 0.1% | 8 years financials |
| News Articles | ~8,200 chars | ~2,050 | 1.8% | 20 articles |
| 8-K Events | Variable | Variable | ~1% | Material events |
| **SEC Sections** | **~445K chars** | **~111K** | **96%** | Raw 10-K/Q text |

**Key insight**: SEC sections dominate the prompt. Using AI summaries instead of raw text would reduce prompt by ~97%.

---

## Model Cost Comparison

**Per brief (116K input tokens + 3K output tokens, full SEC context):**

| Model | Input $/MTok | Output $/MTok | Per Brief |
|-------|--------------|---------------|-----------|
| Gemini 2.5 Flash | $0.15 | $0.60 | **$0.02** |
| GPT-4o Mini | $0.15 | $0.60 | $0.02 |
| Gemini 3 Flash | ~$0.15 | ~$0.60 | ~$0.03 |
| Gemini 3 Pro | $2.00 | $12.00 | **$0.27** |
| GPT-4o | $2.50 | $10.00 | $0.32 |
| Claude 4.5 Sonnet | $3.00 | $15.00 | $0.39 |
| Claude 4.5 Opus | $5.00 | $25.00 | $0.66 |

---

## Cost Scenarios

### Scenario 1: All US Stocks (~5,500), Quarterly
| Model | Per Brief | Quarterly | Monthly Avg |
|-------|-----------|-----------|-------------|
| 2.5 Flash | $0.02 | $110 | **$37** |
| 3 Pro | $0.27 | $1,485 | **$495** |

### Scenario 2: Excellent/Good Stocks (~1,000), Quarterly
| Model | Per Brief | Quarterly | Monthly Avg |
|-------|-----------|-----------|-------------|
| 2.5 Flash | $0.02 | $20 | **$7** |
| 3 Pro | $0.27 | $270 | **$90** |

### Scenario 3: Watchlist (100 stocks), Weekly
| Model | Per Brief | Weekly | Monthly |
|-------|-----------|--------|---------|
| 2.5 Flash | $0.02 | $2 | **$9** |
| 3 Pro | $0.27 | $27 | **$117** |

### Initial Population: 1,000 Stocks (One-Time)
- Gemini 3 Pro: **$270** (or $135 with Batch API)

---

## Processing Time Estimates

| Metric | Value |
|--------|-------|
| TTFT (full SEC context) | ~20 seconds |
| Full generation per brief | ~45 seconds |
| 1,000 stocks sequential | ~12 hours |
| 1,000 stocks parallel (10x) | **~1.5 hours** |
| Daily average (quarterly cycle) | ~11 stocks/day |
| Peak day (earnings season) | ~50-100 stocks |

---

## Optimization Options

| Optimization | Token Savings | Cost Reduction | Trade-off |
|--------------|---------------|----------------|-----------|
| Use AI summaries instead of raw SEC | ~97% | ~85% | Pre-computation needed |
| Truncate Risk Factors to 10K chars | ~35% | ~35% | Some detail lost |
| Fewer news articles (10 vs 20) | ~3% | ~3% | Minimal impact |
| Remove Market Risk section | ~5% | ~5% | Low value anyway |

---

## Recommended Implementation

1. **Pre-compute briefs overnight** for stocks rated Excellent/Good
2. **Use Gemini 3 Pro** for quality ($90/month for 1,000 stocks)
3. **Regenerate on SEC filing changes** (not daily)
4. **Parallel processing** (10 concurrent) for faster batch runs
5. **Keep "Regenerate" button** for on-demand user requests

---

## Current API Tier

- **Paid Tier 1** (Google AI Studio)
- Higher rate limits than free tier
- No provisioned throughput (that requires Vertex AI Enterprise)
- Latency is inherent to model processing, not tier limitations
