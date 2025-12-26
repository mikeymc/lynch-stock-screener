# Stock Detail View: API Call Trees

This document outlines the execution flow for the five critical API endpoints used in the stock detail view. It identifies external calls, blocking operations, and data schemas.

## 1. Get Stock Details
**Endpoint**: `GET /api/stock/<ticker>?algorithm=weighted`
**Handler**: `app.py:get_stock`

### Call Tree
```mermaid
graph TD
    A[GET /api/stock/:ticker] --> B{fetcher.fetch_stock_data}
    B --> C[db.get_stock_metrics]
    B --> D[edgar_fetcher.fetch_stock_fundamentals]
    D --> D1(External: SEC EDGAR API)
    D --> D2(db.save_earnings_history)
    B --> E{If EDGAR Fail / Missing Data}
    E --> F[yf.Ticker.info]
    F --> F1(External: Yahoo Finance API)
    E --> G[yf.Ticker.balance_sheet]
    G --> G1(External: Yahoo Finance API)
    E --> H[yf.Ticker.financials]
    H --> H1(External: Yahoo Finance API)
    E --> I[yf.Ticker.cashflow]
    I --> I1(External: Yahoo Finance API)
    B --> J[db.save_stock_metrics]
    A --> K[criteria.evaluate_stock]
    K --> L(In-Memory Calculation)
```

### Bottlenecks
- **Sequential yfinance calls**: `info`, `balance_sheet`, `financials`, `cashflow` are fetched sequentially if EDGAR data is partial or missing.
- **Blocking I/O**: The main thread blocks while waiting for each external API response.

### Return Schema
```json
{
  "stock_data": {
    "symbol": "AAPL",
    "price": 150.00,
    "pe_ratio": 25.5,
    "market_cap": 2500000000,
    "eps_history": [...],
    "revenue_history": [...]
  },
  "evaluation": {
    "score": 85,
    "rating": "Buy",
    "details": {...}
  }
}
```

---

## 2. Unified Chart Analysis
**Endpoint**: `POST /api/stock/<ticker>/unified-chart-analysis`
**Handler**: `app.py:get_unified_chart_analysis`

### Call Tree
```mermaid
graph TD
    A[POST /api/stock/:ticker/unified-chart-analysis] --> B[db.get_chart_analysis]
    B -->|Cache Hit| C[Return Cached JSON]
    B -->|Cache Miss| D[db.get_filing_sections]
    D --> E{If Missing in DB}
    E --> F[edgar_fetcher.extract_filing_sections]
    F --> F1(External: SEC EDGAR / edgartools)
    F --> F2(Processing: Parsing 10-K/10-Q HTML)
    A --> G[db.get_material_events]
    A --> H[db.get_news_articles]
    A --> I[lynch_analyst.generate_unified_chart_analysis]
    I --> J(External: LLM Inference)
    I --> K[db.set_chart_analysis]
```

### Bottlenecks
- **10-K/10-Q Parsing**: `extract_filing_sections` downloads large HTML files from EDGAR and parses them. This is very slow & CPU intensive.
- **LLM Inference**: Generating the analysis can take 5-10+ seconds depending on the model and prompt size.

---

## 3. Stock History (Charts)
**Endpoint**: `GET /api/stock/<ticker>/history?period_type=annual`
**Handler**: `app.py:get_stock_history`

### Call Tree
```mermaid
graph TD
    A[GET /api/stock/:ticker/history] --> B[db.get_earnings_history]
    A --> C{For Each Year in History}
    C --> D[price_client.get_historical_price]
    D --> E{Check Cache}
    E -->|Miss| F{Loop Regions: NASDAQ, NYSE, AMEX...}
    F --> G(External: TradingView DataFeed)
    G --> H{Exception/Fail?}
    H -->|Yes| I[Retry 3x w/ 1s Sleep]
    E -->|Fail| J[yf.Ticker.history]
    J --> J1(External: Yahoo Finance Fallback)
    A --> K[price_client.get_weekly_price_history]
    K --> L(External: TradingView DataFeed)
```

### Bottlenecks
- **TradingView Retries**: The "Blind Guess" logic iterates exchanges. If a stock is on the 4th exchange (or none), it retries previous ones 3x with 1s sleeps. This is the **primary suspect for the >10s delay**.
- **Sequential Dates**: It fetches historical price for *every fiscal year end* sequentially.

### Return Schema
```json
[
  {
    "year": 2023,
    "eps": 5.0,
    "revenue": 100000,
    "pe_ratio": 20.0,
    "price": 100.0
  },
  ...
]
```

---

## 4. Stock News
**Endpoint**: `GET /api/stock/COST/news`
**Handler**: `app.py:get_stock_news`

### Call Tree
```mermaid
graph TD
    A[GET /api/stock/:ticker/news] --> B[news_client.get_company_news]
    B --> C(External: Finnhub API)
    A --> D[db.save_news_articles]
```

### Return Schema
```json
[
  {
    "headline": "Costco Earnings Beat Expectations",
    "summary": "...",
    "url": "...",
    "source": "Bloomberg",
    "datetime": 1678888888
  }
]
```

---

## 5. Material Events
**Endpoint**: `GET /api/stock/COST/material-events`
**Handler**: `app.py:get_material_events`

### Call Tree
```mermaid
graph TD
    A[GET /api/stock/:ticker/material-events] --> B[sec_client.get_material_events]
    B --> C(External: SEC RSS Feed / API)
    A --> D[db.save_material_events]
```

### Return Schema
```json
[
  {
    "event_type": "8-K",
    "headline": "Entry into a Material Definitive Agreement",
    "description": "...",
    "filing_date": "2023-11-05"
  }
]
```
