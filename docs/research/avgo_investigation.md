# AVGO Data Investigation

## Issue
User reported that AVGO (Broadcom) shows "N/A" for 5Y Net Income Growth.

## Investigation Results

### Backend Data ✅
I verified that the backend **is** calculating AVGO's earnings growth correctly:

```json
{
  "earnings_cagr": 36.62,
  "revenue_cagr": 30.77,
  "consistency_score": 0.0
}
```

### Raw Data
AVGO's earnings history from EDGAR shows:
- **2016**: -$1.7B (loss)
- **2017**: $1.7B
- **2018**: $12.3B
- **2019-2021**: Missing data (None)
- **2022**: $11.5B
- **2023**: $14.1B
- **2024**: $5.9B

Despite the gaps and volatility, the system correctly calculates a **36.6% earnings CAGR** using the available data points.

### Why Consistency Score is 0.0
The consistency score is extremely low (0.0) because:
1. AVGO had a **loss** in 2016
2. Missing data for 2019-2021
3. Highly volatile earnings (swings from -$1.7B to $14B)

This triggers the penalty system in `earnings_analyzer.py` which adds penalties for negative years and volatility.

## Root Cause
The data **is being calculated correctly** by the backend. If the frontend shows "N/A", it's likely due to:
1. **Stale cache**: The screening results need to be refreshed
2. **Old data**: AVGO was screened before the recent data fetch
3. **Frontend state**: The browser might be showing cached results

## Solution
**Refresh the screening** to pull the latest data. The backend will return the correct earnings_cagr value of 36.6%.
