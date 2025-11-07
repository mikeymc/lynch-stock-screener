# Lynch Stock Screener

A full-stack stock screening application that filters NYSE and NASDAQ stocks using Peter Lynch's investment criteria.

## Features

- **Complete Stock Screening**: Analyze all NYSE/NASDAQ stocks (~5000+)
- **Peter Lynch Criteria**:
  - PEG Ratio < 1.0 (PASS), < 1.15 (CLOSE)
  - Debt-to-Equity < 0.5 (PASS), < 0.6 (CLOSE)
  - Institutional Ownership < 50% (PASS), < 55% (CLOSE)
  - 5-year earnings growth (CAGR with consistency analysis)
- **Historical Price Data**: Fetch stock prices at fiscal year-end dates to calculate historical P/E ratios
- **Hybrid Data Sources**:
  - SEC EDGAR API for 10-20 years of fundamental data (EPS, revenue)
  - Schwab API for accurate historical stock prices (optional)
  - Automatic fallback to yfinance when Schwab unavailable
- **Fiscal Year Awareness**: Uses actual fiscal year-end dates (not calendar year) for accurate price/earnings alignment
- **Smart Caching**: 24-hour cache validity for blazing fast subsequent runs
- **Color-Coded Results**: Green (PASS), Yellow (CLOSE), Red (FAIL)
- **Sortable Table**: Click any column header to sort
- **Filter View**: Show only PASS, CLOSE, or FAIL stocks

## Tech Stack

- **Backend**: Python 3.14, Flask, SQLite
- **Frontend**: React 18, Vite
- **Data Sources**:
  - SEC EDGAR API (primary fundamentals source)
  - Schwab Developer API (optional, for historical prices)
  - yfinance (fallback for prices and supplemental data)
- **Testing**: pytest (82 tests, all passing)

## Quick Start

### 1. Backend Setup

```bash
# Create virtual environment with UV
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Run tests (optional)
python -m pytest backend/tests/ -v

# Start Flask API server
cd backend
python app.py
```

Backend will run on `http://localhost:5000`

### 2. Schwab API Setup (Optional)

The app works without Schwab API, falling back to yfinance for historical prices. To enable Schwab:

1. **Get API Credentials** from [Schwab Developer Portal](https://developer.schwab.com/)
2. **Create `.env` file** in the `backend/` directory:

```bash
cp backend/.env.example backend/.env
```

3. **Add your credentials** to `backend/.env`:

```bash
SCHWAB_API_KEY=your_app_key_here
SCHWAB_API_SECRET=your_app_secret_here
SCHWAB_REDIRECT_URI=https://localhost
SCHWAB_TOKEN_PATH=./tokens/schwab_tokens.json
```

4. **First-time OAuth**: On first run, schwab-py will open a browser for OAuth authorization. Follow the prompts and paste the redirect URL back into the terminal.

5. **Token Refresh**: Tokens are automatically refreshed and stored in `./tokens/schwab_tokens.json`

### 3. Frontend Setup

```bash
# Install dependencies
cd frontend
npm install

# Start Vite dev server
npm run dev
```

Frontend will run on `http://localhost:5173`

## Usage

1. **Start both servers** (backend on :5000, frontend on :5173)
2. **Open** `http://localhost:5173` in your browser
3. **Click "Screen 50 Stocks"** to analyze the first 50 NYSE/NASDAQ stocks
4. **Click column headers** to sort by any metric
5. **Use the filter dropdown** to show only PASS, CLOSE, or FAIL stocks
6. **Click "Load Cached Stocks"** on subsequent runs for instant results

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/stock/<symbol>` - Get analysis for single stock
- `GET /api/stock/<symbol>/history` - Get historical EPS, revenue, price, and P/E ratios
- `GET /api/screen?limit=100` - Screen stocks (default 100)
- `GET /api/cached` - View all cached stock analyses

## Peter Lynch Criteria Explained

### PEG Ratio (Price/Earnings to Growth)
- **Target**: < 1.0 (stock is undervalued relative to growth)
- **Formula**: P/E Ratio ÷ Earnings Growth Rate (5-year CAGR)

### Debt-to-Equity Ratio
- **Target**: < 0.5 (conservative debt levels)
- **Higher ratios** indicate more financial risk

### Institutional Ownership
- **Target**: < 50% (room for institutional buyers to drive price up)
- **Lynch's insight**: Undiscovered by Wall Street

### 5-Year Earnings Growth
- **Calculated** using CAGR (Compound Annual Growth Rate)
- **Includes** consistency score (standard deviation of growth rates)

## Project Structure

```
lynch-stock-screener/
├── backend/
│   ├── app.py                 # Flask REST API
│   ├── database.py            # SQLite operations with fiscal year-end support
│   ├── data_fetcher.py        # Hybrid EDGAR + yfinance data fetching
│   ├── edgar_fetcher.py       # SEC EDGAR API client
│   ├── schwab_client.py       # Schwab API client for historical prices
│   ├── earnings_analyzer.py   # 5-year growth calculations
│   ├── lynch_criteria.py      # Criteria evaluation logic
│   ├── .env.example           # Environment variables template
│   └── tests/                 # 82 passing tests
├── frontend/
│   └── src/
│       ├── App.jsx            # Main React component
│       └── App.css            # Styling
├── requirements.txt           # Python dependencies
└── README.md
```

## Development

### Run Backend Tests
```bash
source .venv/bin/activate
python -m pytest backend/tests/ -v
```

### Build Frontend for Production
```bash
cd frontend
npm run build
```

## Notes

- **First run** will be slow (fetching data from SEC EDGAR and yfinance/Schwab)
- **Subsequent runs** use cached data (much faster)
- **Cache expires** after 24 hours
- **EDGAR data** provides 10-20 years of historical fundamentals for most stocks
- **Fiscal year awareness**: Prices are fetched at each company's actual fiscal year-end (e.g., Apple's September 30, not December 31)
- **Schwab API** is optional - the app works fine with yfinance fallback
- **SEC EDGAR** enforces rate limiting (10 requests/second) - the app respects this automatically
- Some stocks may not have sufficient historical data and will be filtered out
- yfinance is unofficial and may occasionally be rate-limited

## License

MIT
