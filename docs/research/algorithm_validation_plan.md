# Algorithm Validation Study - Implementation Plan

## Goal

Run backtests on the full S&P 500 for 1, 3, and 5 years to validate our Lynch scoring algorithm against actual stock performance. Use the results to identify which scoring components correlate best with returns and suggest algorithm improvements.

## Approach

### 1. Data Collection

**S&P 500 Stock List**
- Fetch current S&P 500 constituents (can use Wikipedia, yfinance, or a static list)
- Note: This introduces survivorship bias (stocks currently in S&P 500 vs. those that were)
- For initial analysis, this is acceptable; can enhance later

**Bulk Backtest Runner**
- Create `algorithm_validator.py` to:
  - Run backtests for all S&P 500 stocks
  - Support multiple timeframes (1yr, 3yr, 5yr)
  - Handle errors gracefully (delisted stocks, insufficient data)
  - Show progress during execution
  - Store results in database

### 2. Data Storage

**New Database Table: `backtest_results`**
```sql
CREATE TABLE backtest_results (
    id SERIAL PRIMARY KEY,
    symbol TEXT,
    backtest_date DATE,
    years_back INTEGER,
    start_price REAL,
    end_price REAL,
    total_return REAL,
    historical_score REAL,
    historical_rating TEXT,
    peg_score REAL,
    debt_score REAL,
    ownership_score REAL,
    consistency_score REAL,
    peg_ratio REAL,
    earnings_cagr REAL,
    debt_to_equity REAL,
    institutional_ownership REAL,
    created_at TIMESTAMP,
    UNIQUE(symbol, years_back)
)
```

### 3. Analysis Framework

**Correlation Analysis**
- Score vs. Returns: Does higher historical score predict higher returns?
- Component Analysis: Which components (PEG, debt, ownership) correlate best?
- Score Buckets: Group stocks by score ranges, compare average returns

**Key Metrics to Calculate**
- Correlation coefficient (score vs. return)
- Average return by score bucket (0-20, 20-40, 40-60, 60-80, 80-100)
- Component correlations (each component's score vs. return)
- Best/worst performers by score category

**Statistical Analysis**
- Do "STRONG_BUY" stocks outperform "CAUTION"/"AVOID"?
- Which weight adjustments would improve predictive power?
- Are there sector-specific patterns?

### 4. Implementation Steps

#### Backend Components

**`algorithm_validator.py`**
- `AlgorithmValidator` class
- `run_sp500_backtests(years_back)` - Run all backtests
- `analyze_results(years_back)` - Calculate correlations and insights
- `get_sp500_symbols()` - Fetch S&P 500 list

**Database Updates**
- Add `backtest_results` table to `database.py`
- Add methods: `save_backtest_result()`, `get_backtest_results()`

**API Endpoints**
- `POST /api/validate/run` - Start validation run
- `GET /api/validate/progress` - Check progress
- `GET /api/validate/results/{years_back}` - Get analysis results

#### Frontend Components

**`AlgorithmTuning.jsx`**
- **Manual Tuning Section**:
  - Interactive sliders for weights (PEG, Consistency, Debt, Ownership)
  - Sliders for thresholds (PEG excellent/good/fair, Debt levels, etc.)
  - "Rerun Backtest" button to test current configuration
  - Real-time results update
- **Auto-Optimization Section**:
  - "Auto-Optimize" button to start optimization
  - Progress indicator showing iterations
  - Best configuration found display
  - Optimization history chart
  - "Apply Configuration" button to save and use
- **Results Display**:
  - Score vs. Return scatter plot
  - Average return by score bucket (bar chart)
  - Component correlation comparison
  - Current vs. Optimized comparison
  - Recommendations section

### 5. Auto-Optimization Engine

**Optimization Strategy**
Use gradient descent or genetic algorithm to find optimal weights:

**Objective Function**: Maximize correlation between score and returns

**Parameters to Optimize**:
- Weight: PEG (currently 0.50)
- Weight: Consistency (currently 0.25)
- Weight: Debt (currently 0.15)
- Weight: Ownership (currently 0.10)
- Constraint: Weights must sum to 1.0

**Algorithm**: Gradient Descent
1. Start with current weights
2. For each iteration:
   - Calculate gradients (how changing each weight affects correlation)
   - Update weights in direction that improves correlation
   - Ensure weights stay valid (0-1, sum to 1)
3. Stop when correlation stops improving
4. Track best configuration found

**Alternative**: Genetic Algorithm
- Generate population of random weight combinations
- Evaluate fitness (correlation) for each
- Select best performers
- Create new generation through crossover and mutation
- Repeat for N generations

**Implementation**:
```python
class AlgorithmOptimizer:
    def optimize(self, backtest_results, max_iterations=100):
        # Gradient descent implementation
        best_config = current_config
        best_correlation = calculate_correlation(results, current_config)
        
        for i in range(max_iterations):
            gradients = calculate_gradients(results, current_config)
            new_config = update_weights(current_config, gradients)
            new_correlation = calculate_correlation(results, new_config)
            
            if new_correlation > best_correlation:
                best_config = new_config
                best_correlation = new_correlation
            else:
                break  # Converged
        
        return best_config, best_correlation
```

**Database Storage**:
```sql
CREATE TABLE algorithm_configurations (
    id SERIAL PRIMARY KEY,
    name TEXT,
    weight_peg REAL,
    weight_consistency REAL,
    weight_debt REAL,
    weight_ownership REAL,
    correlation_1yr REAL,
    correlation_3yr REAL,
    correlation_5yr REAL,
    is_active BOOLEAN,
    created_at TIMESTAMP
)

CREATE TABLE optimization_runs (
    id SERIAL PRIMARY KEY,
    years_back INTEGER,
    iterations INTEGER,
    initial_correlation REAL,
    final_correlation REAL,
    improvement REAL,
    best_config_id INTEGER REFERENCES algorithm_configurations(id),
    created_at TIMESTAMP
)
```

### 6. Execution Plan

**Phase 1: Infrastructure (Day 1)**
- Add database table
- Create `AlgorithmValidator` class
- Implement S&P 500 symbol fetching
- Implement bulk backtest runner

**Phase 2: Analysis (Day 2)**
- Implement correlation analysis
- Calculate score bucket statistics
- Generate insights and recommendations

**Phase 3: Frontend (Day 3)**
- Create validation UI
- Add charts for visualization
- Display recommendations

**Phase 4: First Run & Iteration**
- Run 1-year backtests first (faster)
- Analyze results
- Run 3-year and 5-year if 1-year looks promising

### 6. Expected Insights

From this analysis, we'll learn:
- Does our algorithm predict stock performance?
- Should we adjust component weights?
- Are certain components (PEG, debt) more predictive?
- Do we need sector-specific scoring?
- Should we add new factors?

### 7. Potential Algorithm Tweaks

Based on results, we might:
- Adjust weights (currently: PEG 50%, Consistency 25%, Debt 15%, Ownership 10%)
- Add/remove scoring components
- Implement sector-specific scoring
- Adjust score thresholds for ratings
- Add momentum or trend factors

### 8. Performance Optimizations

**Implement All Optimizations**:

1. **Background Thread**
   - Run validation in separate thread
   - Don't block API responses
   - Store progress in database

2. **Price History Caching**
   - Cache fetched price data between timeframes
   - Reuse 1-year data for 3-year and 5-year runs
   - Store in memory during validation run

3. **Parallelization with Thread Pool**
   - Use `concurrent.futures.ThreadPoolExecutor`
   - Limit to 5-10 concurrent threads (respect yfinance rate limits)
   - Process stocks in batches

4. **Batch Processing**
   - Process in chunks of 50 stocks
   - Commit results after each batch
   - Allow resuming if interrupted

**Implementation**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

class AlgorithmValidator:
    def __init__(self, db):
        self.db = db
        self.price_cache = {}  # Cache price history
        
    def run_sp500_backtests(self, years_back, max_workers=5):
        symbols = self.get_sp500_symbols()
        results = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self._backtest_with_cache, sym, years_back): sym 
                      for sym in symbols}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        self.db.save_backtest_result(result)
                except Exception as e:
                    logger.error(f"Backtest failed: {e}")
        
        return results
```

### 9. Historical Data Limitations

**Current Approximations** (where we use current data as proxy for historical):

1. **Institutional Ownership** (`backtester.py:143`)
   - Uses current `institutional_ownership` value
   - Historical ownership data not readily available
   - Impact: Ownership score may not reflect actual historical conditions
   - Potential Fix: Could fetch from SEC filings, but complex

2. **Market Cap Calculation** (`backtester.py:129-133`)
   - Approximates historical market cap using:
     - `historical_market_cap = historical_price * (current_market_cap / current_price)`
   - Assumes share count hasn't changed dramatically
   - Impact: May be inaccurate if stock splits or major dilution occurred
   - Potential Fix: Would need historical share count data

3. **Sector Classification** (`backtester.py:146`)
   - Uses current sector assignment
   - Companies occasionally change sectors
   - Impact: Minimal, sectors rarely change

4. **Revenue CAGR** ~~(backtester.py:141)~~ **✅ IMPLEMENTED**
   - ~~Currently marked as TODO~~
   - ~~Not implemented for historical reconstruction~~
   - Now implemented using historical revenue data
   - Impact: Revenue growth component now included in historical scores

**Improvements Made**:
- ✅ **Switched to Net Income for Growth Calculations**: More stable than EPS, immune to stock splits
- ✅ **Implemented Revenue CAGR**: Now calculated from historical revenue data
- ✅ **Synthetic EPS Calculation**: Estimates EPS from net income when needed for P/E ratio

**Data We DO Have Historically**:
- ✅ Stock prices (from yfinance)
- ✅ Earnings per share (from our database)
- ✅ Revenue (from our database)
- ✅ Debt-to-Equity (from our database)
- ✅ Dividend amounts (from our database)

### 10. Limitations

**Runtime Estimate**
- S&P 500 = ~500 stocks
- ~3 seconds per backtest (yfinance API calls)
- Total: ~25 minutes per timeframe
- All three timeframes: ~75 minutes

**Optimization**
- Run in background thread
- Cache price history between timeframes
- Parallelize with thread pool (careful with yfinance rate limits)
- Consider running overnight or in batches

### 9. Limitations

- **Survivorship Bias**: Only current S&P 500 members
- **Historical Score Approximations**: Some metrics use current data as proxy
- **Data Quality**: Depends on yfinance data availability
- **Market Conditions**: Past performance doesn't guarantee future results

## Next Steps

1. Review this plan with user
2. Get approval to proceed
3. Start with Phase 1: Infrastructure
4. Run initial 1-year validation
5. Review results and iterate
