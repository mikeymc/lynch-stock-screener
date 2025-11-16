# Stock Split Issue Analysis

## Executive Summary

**CRITICAL ISSUE FOUND**: Historical P/E ratios and other per-share metrics are **incorrectly calculated** because:
- ✅ Stock **prices** from yfinance are **split-adjusted**
- ❌ **EPS data** from EDGAR/yfinance is **NOT split-adjusted**

This creates a **price/EPS mismatch** that produces invalid P/E ratios for any period before a stock split.

---

## The Problem Illustrated

### Example: Company XYZ has a 2:1 stock split in 2020

| Metric | 2018 Original | 2018 After Split | What We Use | Result |
|--------|--------------|------------------|-------------|---------|
| **Stock Price** | $100 | $50 (adjusted) | $50 ✓ | Split-adjusted |
| **EPS** | $4.00 | $2.00 (adjusted) | $4.00 ❌ | NOT adjusted |
| **P/E Ratio** | 25.0 | 25.0 (correct) | **12.5** ❌ | **WRONG!** |

**Current Calculation**: `P/E = $50 / $4.00 = 12.5` ❌
**Correct Calculation**: `P/E = $50 / $2.00 = 25.0` ✓

---

## Real-World Impact Examples

### Apple (AAPL) - Has had multiple splits
- **4:1 split on August 31, 2020**
- **7:1 split on June 9, 2014**

For any earnings data from 2010-2013:
- Price is adjusted by factor of **28x** (4 × 7)
- EPS is **NOT adjusted**
- **P/E ratios are off by 28x!**

### NVIDIA (NVDA) - Recent 10:1 split
- **10:1 split on June 10, 2024**

For 2023 earnings:
- Price divided by 10 ✓
- EPS **NOT** divided by 10 ❌
- P/E ratio is **10x too low**

### Tesla (TSLA) - Multiple splits
- **3:1 split on August 25, 2022**
- **5:1 split on August 31, 2020**

Pre-2020 data:
- Price adjusted by **15x** (3 × 5)
- EPS not adjusted
- **Invalid historical comparisons**

---

## Current Implementation Analysis

### Where Price Data Comes From
**File**: `backend/app.py:227` and `backend/app.py:241`

```python
hist = ticker.history(start=start_date, end=end_date)
price = hist.iloc[-1]['Close']
```

**yfinance behavior**: `.history()` returns **split-adjusted prices by default**

### Where EPS Data Comes From

**Primary Source**: EDGAR SEC filings
**File**: `backend/edgar_fetcher.py:116-179`
- Parses `EarningsPerShareDiluted` from XBRL data
- Values are **as-reported** (not split-adjusted)

**Fallback Source**: yfinance financials
**File**: `backend/data_fetcher.py:228-299`
- Uses `stock.financials` for income statements
- Values are **as-reported** (not split-adjusted)

### Where P/E is Calculated
**File**: `backend/app.py:249-257`

```python
if price is not None and eps > 0:
    pe_ratio = price / eps  # ← MISMATCH HERE!
    pe_ratios.append(pe_ratio)
```

**Problem**: Dividing split-adjusted price by non-adjusted EPS

---

## Available Data from yfinance

Based on yfinance documentation and source code, these attributes are available:

### 1. `.splits` - Stock Split History
```python
ticker = yf.Ticker("AAPL")
splits = ticker.splits

# Returns pandas Series:
# 2014-06-09    7.0
# 2020-08-31    4.0
# dtype: float64
```

### 2. `.actions` - Combined Corporate Actions
```python
actions = ticker.actions

# Returns DataFrame with columns:
# - Dividends (dividend amount)
# - Stock Splits (split ratio)
```

### 3. `.history()` with `auto_adjust` parameter
```python
# Split-adjusted prices (default)
hist_adjusted = ticker.history(start="2010-01-01", auto_adjust=True)

# Unadjusted prices
hist_unadjusted = ticker.history(start="2010-01-01", auto_adjust=False)
```

### 4. `.history()` with `actions=True`
```python
hist = ticker.history(start="2010-01-01", actions=True)

# Includes 'Dividends' and 'Stock Splits' columns
# Shows split ratio on split dates
```

---

## Proposed Solution

### Option 1: Adjust EPS for Splits (RECOMMENDED)

**Approach**: Fetch stock split history and adjust historical EPS to match adjusted prices

**Steps**:
1. Fetch split history using `ticker.splits`
2. Calculate cumulative adjustment factor for each year
3. Adjust stored EPS by the factor before calculating P/E
4. Store splits in database for caching

**Advantages**:
- ✅ All ratios become comparable over time
- ✅ Matches how financial analysts view data
- ✅ Consistent with industry standard (most platforms show adjusted EPS)
- ✅ Minimal changes to existing calculations

**Implementation Locations**:
- Add `stock_splits` table to database
- Modify `backend/data_fetcher.py` to fetch splits
- Modify `backend/app.py:249-257` to apply adjustment before calculating P/E
- Update `backend/database.py` for split storage

### Option 2: Use Unadjusted Prices

**Approach**: Change price fetching to use `auto_adjust=False`

**Steps**:
1. Modify `ticker.history()` calls to use `auto_adjust=False`
2. Keep EPS as-is

**Disadvantages**:
- ❌ Prices won't match what users see on charts
- ❌ Inconsistent with market convention
- ❌ Makes historical price comparisons difficult
- ❌ Still need to adjust dividends separately

**Verdict**: NOT RECOMMENDED

### Option 3: Hybrid Approach

**Approach**: Store both adjusted and unadjusted values

**Advantages**:
- ✅ Maximum flexibility
- ✅ Can show either view to users

**Disadvantages**:
- ❌ Doubles storage requirements
- ❌ More complex queries
- ❌ Confusing for users

**Verdict**: Overkill for current needs

---

## Recommended Implementation Details

### 1. Database Schema Addition

```sql
CREATE TABLE stock_splits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    split_date TEXT NOT NULL,
    split_ratio REAL NOT NULL,  -- e.g., 2.0 for 2:1 split
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, split_date)
);

CREATE INDEX idx_stock_splits_symbol ON stock_splits(symbol);
CREATE INDEX idx_stock_splits_date ON stock_splits(split_date);
```

### 2. Fetch Split Data

**New function in `backend/data_fetcher.py`**:

```python
def fetch_stock_splits(symbol: str) -> list:
    """
    Fetch historical stock splits from yfinance

    Returns list of dicts: [{'date': '2020-08-31', 'ratio': 4.0}, ...]
    """
    ticker = yf.Ticker(symbol)
    splits = ticker.splits

    if splits.empty:
        return []

    split_list = []
    for date, ratio in splits.items():
        split_list.append({
            'date': date.strftime('%Y-%m-%d'),
            'ratio': float(ratio)
        })

    return split_list
```

### 3. Calculate Cumulative Adjustment Factor

**New function in `backend/data_fetcher.py`**:

```python
def get_split_adjustment_factor(symbol: str, target_date: str) -> float:
    """
    Calculate cumulative split adjustment factor from target_date to present

    For a 2:1 split in 2020 and 4:1 split in 2024:
    - Data from 2018: factor = 2.0 * 4.0 = 8.0 (divide EPS by 8)
    - Data from 2022: factor = 4.0 (divide EPS by 4)
    - Data from 2024: factor = 1.0 (no adjustment needed)

    Returns: float (cumulative split ratio)
    """
    from datetime import datetime

    splits = db.get_stock_splits(symbol)

    target = datetime.strptime(target_date, '%Y-%m-%d')
    factor = 1.0

    for split in splits:
        split_date = datetime.strptime(split['date'], '%Y-%m-%d')

        # If split occurred AFTER the target date, we need to adjust
        if split_date > target:
            factor *= split['ratio']

    return factor
```

### 4. Adjust EPS in P/E Calculation

**Modify `backend/app.py:249-257`**:

```python
# Calculate P/E ratio if we have price and positive EPS
if price is not None and eps > 0:
    # ADJUSTMENT FOR STOCK SPLITS
    # Get the fiscal year end date or default to Dec 31
    fiscal_date = fiscal_end if fiscal_end else f"{year}-12-31"

    # Calculate split adjustment factor
    adjustment_factor = get_split_adjustment_factor(symbol.upper(), fiscal_date)

    # Adjust EPS to match split-adjusted price
    adjusted_eps = eps / adjustment_factor

    # Calculate P/E with adjusted EPS
    pe_ratio = price / adjusted_eps
    pe_ratios.append(pe_ratio)
    prices.append(price)
    eps_values.append(adjusted_eps)  # Store adjusted EPS for display
else:
    pe_ratios.append(None)
    prices.append(None)
```

### 5. Database Storage Functions

**Add to `backend/database.py`**:

```python
def save_stock_splits(self, symbol: str, splits: list):
    """Save stock split history"""
    cursor = self.conn.cursor()

    for split in splits:
        cursor.execute('''
            INSERT OR REPLACE INTO stock_splits
            (symbol, split_date, split_ratio, last_updated)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (symbol, split['date'], split['ratio']))

    self.conn.commit()

def get_stock_splits(self, symbol: str) -> list:
    """Get stock split history, ordered by date"""
    cursor = self.conn.cursor()
    cursor.execute('''
        SELECT split_date, split_ratio
        FROM stock_splits
        WHERE symbol = ?
        ORDER BY split_date ASC
    ''', (symbol,))

    return [
        {'date': row[0], 'ratio': row[1]}
        for row in cursor.fetchall()
    ]
```

---

## Testing Strategy

### Test Cases

1. **Stocks with recent splits**:
   - AAPL (4:1 in 2020, 7:1 in 2014)
   - NVDA (10:1 in 2024)
   - TSLA (3:1 in 2022, 5:1 in 2020)
   - GOOGL (20:1 in 2022)

2. **Stocks with no splits**:
   - BRK.A (Berkshire Hathaway - never split)
   - Verify factor = 1.0, no adjustment

3. **Verification method**:
   ```python
   # For any year, verify:
   adjusted_eps = original_eps / split_factor
   pe_ratio = split_adjusted_price / adjusted_eps

   # Should match:
   pe_ratio_check = unadjusted_price / original_eps
   ```

### Manual Verification Example

**Apple (AAPL) - 2013 Data**

```
Known values from public sources:
- 2013 Fiscal Year End: Sep 28, 2013
- 2013 Reported EPS: ~$40.03 (annual)
- 2013 Year-end Price (unadjusted): ~$560
- Splits since then: 7:1 (2014) + 4:1 (2020) = 28x

Expected adjusted values:
- Adjusted EPS: $40.03 / 28 = ~$1.43
- Adjusted Price: $560 / 28 = ~$20
- P/E Ratio: $20 / $1.43 ≈ 14.0

Test that our calculation produces P/E ≈ 14.0
```

---

## Migration Plan

### Phase 1: Add Split Tracking (No Breaking Changes)
1. Add `stock_splits` table to database
2. Add split fetching functions
3. Populate splits for existing stocks
4. **No changes to calculations yet**

### Phase 2: Implement Adjustment (Fixes P/E Ratios)
1. Add `get_split_adjustment_factor()` function
2. Modify P/E calculation to adjust EPS
3. Add tests for split-adjusted calculations
4. Deploy and monitor

### Phase 3: Update UI (Show Adjusted Data)
1. Update frontend to show "Split-adjusted EPS"
2. Add tooltip explaining adjustment
3. Optionally show both adjusted and reported values

### Phase 4: Backfill (Fix Historical Data)
1. Run backfill script for all existing stocks
2. Recalculate and cache split factors
3. Verify against known benchmarks

---

## Data Validation

### How to Verify Correctness

1. **Compare with Financial Sites**:
   - Yahoo Finance (shows adjusted EPS)
   - MarketWatch
   - Morningstar

2. **Cross-check P/E Ratios**:
   - Current P/E should match `yfinance.Ticker().info['trailingPE']`
   - Historical P/E should be consistent across years

3. **Spot Check Calculations**:
   ```python
   # For any stock:
   current_price / current_eps = current_pe  # Should match yfinance
   historical_price / adjusted_historical_eps = historical_pe  # Should be reasonable
   ```

---

## Conclusion

**Current State**: ❌ Historical P/E ratios are **incorrect** for any stock that has split

**Recommended Action**: ✅ Implement Option 1 (Adjust EPS for Splits)

**Effort**: ~4-6 hours of development + testing

**Impact**: 🎯 **Critical** - Affects core functionality of stock screening

**Priority**: **HIGH** - This is a data integrity issue that affects investment decisions

---

## Questions to Address

1. **Should we show both adjusted and reported EPS?**
   - Recommendation: Show adjusted by default with "(adjusted)" label
   - Optionally show reported EPS in detailed view

2. **What about reverse splits?**
   - Same logic applies (ratio < 1.0, e.g., 0.5 for 1:2 reverse split)
   - Algorithm handles this automatically

3. **How often to refresh split data?**
   - Fetch on every stock update (splits are rare)
   - Or: Fetch once, cache in database, refresh monthly

4. **What about other per-share metrics?**
   - Book value per share - YES, needs adjustment
   - Revenue per share - YES, needs adjustment
   - Free cash flow per share - YES, needs adjustment
   - Dividends per share - Already adjusted by yfinance

---

**Next Steps**: Review this analysis and approve implementation plan before proceeding with code changes.
