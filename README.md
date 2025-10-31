# Lynch Stock Screener

Stock screening application that filters NYSE and NASDAQ stocks based on Peter Lynch investment criteria.

## Features

- Screen all NYSE/NASDAQ stocks
- Peter Lynch criteria filtering (PEG ratio, debt-to-equity, earnings growth, institutional ownership)
- 5-year earnings trend analysis
- Caching for fast subsequent runs
- Flag stocks as "PASS", "CLOSE", or "FAIL"

## Tech Stack

- Backend: Python, Flask, SQLite
- Frontend: React
- Data: yfinance

## Setup

```bash
# Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## Running

```bash
# Backend
cd backend
python app.py

# Frontend
cd frontend
npm start
```
