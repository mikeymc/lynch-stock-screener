#!/usr/bin/env python3
# Test to verify Net Income is being stored correctly

import sqlite3
from data_fetcher import DataFetcher
from database import Database

# Initialize
db = Database('stocks.db')
fetcher = DataFetcher(db)

# Force refresh AAPL
print("Fetching AAPL data (force refresh)...")
fetcher.fetch_stock_data('AAPL', force_refresh=True)

# Query annual and quarterly Net Income
conn = db.get_connection()
cursor = conn.cursor()

print("\n=== Annual Net Income for AAPL ===")
cursor.execute("""
    SELECT year, net_income, revenue, period
    FROM earnings_history
    WHERE symbol = 'AAPL' AND period = 'annual'
    ORDER BY year DESC
    LIMIT 10
""")

annual = cursor.fetchall()
print(f"Total annual records: {len(annual)}")
for year, ni, revenue, period in annual:
    ni_str = f"${ni:,.0f}" if ni else "None"
    rev_str = f"${revenue:,.0f}" if revenue else "None"
    print(f"  {year}: NI={ni_str}, Revenue={rev_str}")

print("\n=== Quarterly Net Income for AAPL ===")
cursor.execute("""
    SELECT year, period, net_income
    FROM earnings_history
    WHERE symbol = 'AAPL' AND period != 'annual'
    ORDER BY year DESC, period
""")

quarters = cursor.fetchall()
print(f"Total quarterly records: {len(quarters)}")

if quarters:
    print("\nFirst 20 quarters:")
    for i, (year, period, ni) in enumerate(quarters[:20]):
        ni_str = f"${ni:,.0f}" if ni else "None"
        print(f"  {year} {period}: NI={ni_str}")

conn.close()
print("\nDone!")
