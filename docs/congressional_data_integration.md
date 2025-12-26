# Congressional Trading Integration

## Overview
This feature integrates congressional trading data (purchases and sales by members of the US House and Senate) into the Lynch Stock Screener. It allows users to see if influential politicians are buying or selling specific stocks, which can serve as an alternative data signal for investment decisions.

## Data Source
We use **House Stock Watcher** and **Senate Stock Watcher** as our primary data sources. These are community-maintained projects that digitize and structure the public financial disclosures released by the US Government.

*   **House Stock Watcher**: `https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json`
*   **Senate Stock Watcher**: `https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json`

### Why these sources?
*   **Cost**: They are free to use (Open Data), unlike commercial APIs (e.g., Finnhub, Quiver Quantitative) which often charge significant monthly fees for this specific dataset.
*   **Latency**: While slightly slower than direct real-time scraping, the daily updates are sufficient for long-term investment analysis (the primary use case of this screener).
*   **Structure**: Data is provided in clean, consistent JSON format.

## Architecture

### 1. Database
A new table `congressional_trades` stores the transaction data.

```sql
CREATE TABLE congressional_trades (
    id SERIAL PRIMARY KEY,
    symbol TEXT REFERENCES stocks(symbol),
    politician_name TEXT,
    chamber TEXT,            -- 'House' or 'Senate'
    party TEXT,             -- 'Democrat', 'Republican', etc.
    transaction_date DATE,
    reporting_date DATE,
    transaction_type TEXT,  -- 'Purchase', 'Sale_Full', 'Sale_Partial', 'Exchange'
    amount_min REAL,        -- Lower bound of transaction value (e.g. 1000)
    amount_max REAL,        -- Upper bound of transaction value (e.g. 15000)
    last_updated TIMESTAMP
);
```

### 2. Backend Worker
A new job type `congressional_cache` in the background worker:
1.  Fetches the full JSON datasets from the S3 buckets.
2.  Parses the JSON, normalizing field names (which differ slightly between House and Senate datasets).
3.  Filters for transactions related to stocks currently in our `stocks` table.
4.  Updates the `congressional_trades` table, avoiding duplicates based on unique composite keys (politician, date, ticker, amount).

### 3. API
A new endpoint serves this data to the frontend:
*   `GET /api/stock/<symbol>/congressional`: Returns a list of trades for the given symbol, sorted by transaction date (descending).

### 4. Frontend
The Stock Detail page includes a "Congressional Trading" section (or tab).
*   Displays a table of recent trades.
*   Shows summary statistics (e.g., "Net Buying by Party").
*   Highlights significant trades (large amounts).

## Implementation Details

### Data Normalization
The raw data contains ranges for transaction amounts (e.g., "$1,001 - $15,000"). We parse these into `amount_min` and `amount_max` columns to allow for numerical analysis and filtering.

### Scheduled Updates
The `congressional_cache` job is scheduled to run daily (e.g., at 2:00 AM ET) to pick up new disclosures filed the previous day.

## Future Improvements
*   **Politician Performance**: Track the performance of individual politicians' trades to identify "super traders".
*   **Alerts**: Notify users when a followed politician trades a stock in their watchlist.
*   **Aggregate Sentiment**: Calculate a "Congressional Sentiment Score" for each stock.
