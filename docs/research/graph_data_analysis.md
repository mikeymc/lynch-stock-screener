# Graph Data Issues Analysis

## Issue Summary

After investigating the recent changes to the screening job implementation, I've identified three key issues with missing graph data and database relationships.

---

## Issue 1: `price_history` Table Population

### Your Concern
> "you said the price_history table is only populated during 'backtesting'. that is not right, is it? i believe you mean it is populated during the 'price_history_cache' job?"

### The Truth
**You are correct to question this!** I was wrong. Let me clarify:

- **`price_history` table**: Only populated by the **backtester** ([backtester.py:43](file:///Users/mikey/workspace/lynch-stock-screener/backend/backtester.py#L43))
- **`weekly_prices` table**: Populated by the **`price_history_cache` job** ([price_history_fetcher.py:43](file:///Users/mikey/workspace/lynch-stock-screener/backend/price_history_fetcher.py#L43))

These are **two separate tables** with different purposes:

| Table | Populated By | Purpose | Data Format |
|-------|-------------|---------|-------------|
| `price_history` | Backtester only | Daily price data for backtesting | Daily OHLCV data |
| `weekly_prices` | `price_history_cache` job | Weekly price data for charts | Weekly closing prices |

### The Problem
The `/api/stock/<symbol>/history` endpoint tries to fetch fiscal year-end prices from `price_history` ([app.py:915](file:///Users/mikey/workspace/lynch-stock-screener/backend/app.py#L915)), but this table is **empty** unless you've run backtests. This causes:
- Missing price points on annual charts
- Missing P/E ratio calculations (requires price)

---

## Issue 2: Missing Dividend Yield Data

### Your Concern
> "i see that the dividends chart data is coming back null consistently from the backend for recently screened stocks that pay dividends"

### Root Cause
The dividend yield calculation **requires price history** to work. Looking at [data_fetcher.py:463-481](file:///Users/mikey/workspace/lynch-stock-screener/backend/data_fetcher.py#L463-L481):

```python
# Calculate dividend yield if we have price history and fiscal_end
dividend_yield = None
if dividend and fiscal_end and price_history is not None and not price_history.empty:
    try:
        # Find the closest price on or before the fiscal end date
        idx = price_history.index.get_indexer([fiscal_date], method='nearest')[0]
        if idx != -1:
            price_at_date = price_history.iloc[idx]['Close']
            if price_at_date > 0:
                dividend_yield = (dividend / price_at_date) * 100
    except Exception as e:
        logger.debug(f"[{symbol}] Error calculating yield for {year}: {e}")
```

**The problem**: When using TradingView cache during screening, `price_history` is **NOT fetched** ([data_fetcher.py:284-286](file:///Users/mikey/workspace/lynch-stock-screener/backend/data_fetcher.py#L284-L286)):

```python
# Fetch price history for yield calculation (SKIP if using TradingView cache)
price_history = None
if not using_tradingview_cache:
    price_history = self._get_yf_history(symbol)
```

Since you're using TradingView cache for bulk screening (which is fast), `price_history` is `None`, so **dividend yield is never calculated** even though dividend amounts are captured from EDGAR.

---

## Issue 3: Database Relationship Integrity

### Your Concern
> "if i run a fetch for earnings history and then do another screen, will my earnings history lose its reference to the stock and need to be fetched again?"

### The Good News
**No, your data is safe!** The foreign key relationships do **NOT** use `ON DELETE CASCADE` for most data tables.

Looking at the schema ([database.py:363-869](file:///Users/mikey/workspace/lynch-stock-screener/backend/database.py#L363-L869)):

#### Tables WITH Cascade Delete (will be wiped if stock is deleted):
- `stock_metrics` - Current market data (expected to be refreshed)
- User-specific data: `watchlist`, `chart_analyses`, `lynch_analyses`, `conversations`
- Session data: `screening_results` (tied to sessions, not stocks)

#### Tables WITHOUT Cascade Delete (persistent across screenings):
- ✅ `earnings_history` - **Safe** - Historical earnings data persists
- ✅ `price_history` - **Safe** - Price data persists  
- ✅ `weekly_prices` - **Safe** - Weekly price data persists
- ✅ `sec_filings` - **Safe** - SEC filing metadata persists
- ✅ `filing_sections` - **Safe** - 10-K/10-Q sections persist
- ✅ `news_articles` - **Safe** - News articles persist
- ✅ `material_events` - **Safe** - 8-K events persist

### How It Works
When you run a new screening:
1. The `stocks` table is updated with new/updated stock info
2. `stock_metrics` is overwritten (current price, P/E, etc.)
3. **Historical data** (`earnings_history`, `weekly_prices`, etc.) is preserved via `ON CONFLICT` upserts
4. If a stock is **removed** from the screening (no longer in TradingView results), its historical data remains in the database

---

## Recommended Solutions

### Solution 1: Fix Dividend Yield Calculation
**Option A**: Always fetch price history during screening (slower but complete)
- Remove the `if not using_tradingview_cache` check
- Accept slower screening times

**Option B**: Backfill dividend yields after screening
- Run a separate job to calculate yields using cached `weekly_prices`
- Faster screening, deferred calculation

### Solution 2: Unify Price Data Sources
The dual-table approach (`price_history` vs `weekly_prices`) is confusing. Consider:
- Use `weekly_prices` for **both** charts and fiscal year-end lookups
- Deprecate `price_history` or use it only for backtesting
- Update [app.py:915](file:///Users/mikey/workspace/lynch-stock-screener/backend/app.py#L915) to query `weekly_prices` instead

### Solution 3: Add Price History to Screening Pipeline
Automatically trigger `price_history_cache` job after screening completes, or integrate it into the screening workflow for critical stocks.

---

## Questions for You

1. **Dividend Yield Priority**: How important is it to have dividend yield data immediately after screening? Can it be calculated in a follow-up job?

2. **Price Data Strategy**: Should we consolidate the two price tables, or keep them separate for different purposes?

3. **Screening Performance**: Are you willing to accept slower screening times to get complete data, or prefer fast screening with deferred data enrichment?
