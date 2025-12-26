# Yahoo Finance API Rate Limiting Issue

## Problem

The Yahoo Finance v7 API (`query2.finance.yahoo.com/v7/finance/quote`) is now:
1. **Requiring authentication** - Got 401 Unauthorized initially
2. **Aggressively rate limiting** - Got 429 Too Many Requests after just a few test calls

This makes the direct v7 bulk API approach unreliable for production use.

## Alternative Approaches

### Option 1: Use yfinance Bulk Download (Recommended)

**Approach**: Use yfinance's built-in `download()` function which fetches multiple tickers in one call.

**Code**:
```python
import yfinance as yf

# Download multiple tickers at once
data = yf.download(
    tickers=['AAPL', 'MSFT', 'GOOGL', ...],  # Up to ~100-200 per call
    period='1d',
    group_by='ticker',
    threads=True
)

# Extract current prices
for ticker in tickers:
    price = data[ticker]['Close'].iloc[-1]
```

**Pros**:
- Uses yfinance's internal batching (more reliable than raw API)
- Still significantly faster than individual calls
- Maintained library with fallback mechanisms
- Can batch 100-200 stocks per call

**Cons**:
- Still uses yfinance (you wanted to remove it)
- Not as fast as raw v7 API would be (if it worked)
- ~50-100 requests for 10K stocks vs ~20 with raw API

**Performance**: ~2-3 minutes for 10K stocks (vs 3 hours individual, vs 40s with raw v7)

### Option 2: Optimize Current Setup

**Approach**: Keep yfinance + SEC cache, add threading/async for yfinance calls.

**Code**:
```python
from concurrent.futures import ThreadPoolExecutor

def fetch_market_data_parallel(symbols, max_workers=10):
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(yf.Ticker(s).info): s for s in symbols}
        results = {}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                results[symbol] = future.result()
            except:
                pass
        return results
```

**Pros**:
- Simple to implement
- No new dependencies or API risks
- SEC cache already gives 100x speedup for fundamentals

**Cons**:
- Still slow for market data (~30-60 min for 10K stocks with threading)
- Keeps yfinance dependency

### Option 3: Retry v7 API with Delays

**Approach**: Wait for rate limit to clear, add longer delays between batches.

**Code**:
```python
# Increase delay to 2-5 seconds between batches
fetcher = YahooBulkFetcher(delay_between_batches=5.0)

# Or implement exponential backoff on 429
```

**Pros**:
- Fastest if it works (~40s for 10K stocks)
- No yfinance dependency

**Cons**:
- Unreliable - Yahoo may tighten restrictions further
- Rate limits may persist
- Undocumented API can break anytime

## Recommendation

**Go with Option 1: yfinance bulk download**

**Reasoning**:
- Middle ground between speed and reliability
- ~2-3 minutes for 10K stocks (vs 3 hours) = **60-90x faster**
- Combined with SEC cache, total screening time: **~3-4 minutes** (vs hours)
- More maintainable than raw API hacking
- Can revisit v7 API later if Yahoo opens it up

**Implementation**:
1. Create `yahoo_batch_fetcher.py` using `yf.download()`
2. Batch stocks in groups of 100-150
3. Extract price, P/E, market cap, etc. from results
4. Same integration as planned (prefetch before screening)

Want to proceed with this approach?
