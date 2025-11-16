#!/usr/bin/env python3
"""Test script to check stock split data availability from yfinance"""

import yfinance as yf
from datetime import datetime

# Test with stocks that have had recent splits
test_symbols = ['AAPL', 'TSLA', 'NVDA', 'GOOGL']

for symbol in test_symbols:
    print(f"\n{'='*60}")
    print(f"Testing {symbol}")
    print('='*60)

    ticker = yf.Ticker(symbol)

    # Check for splits attribute
    try:
        splits = ticker.splits
        if not splits.empty:
            print(f"\n✓ Stock splits found for {symbol}:")
            print(splits)
            print(f"\nTotal splits: {len(splits)}")

            # Show the most recent split
            if len(splits) > 0:
                last_split_date = splits.index[-1]
                last_split_ratio = splits.iloc[-1]
                print(f"\nMost recent split:")
                print(f"  Date: {last_split_date.strftime('%Y-%m-%d')}")
                print(f"  Ratio: {last_split_ratio}")
        else:
            print(f"✗ No stock splits found for {symbol}")
    except Exception as e:
        print(f"✗ Error getting splits: {e}")

    # Check for actions (includes splits and dividends)
    try:
        actions = ticker.actions
        if not actions.empty:
            # Filter to just splits (non-zero 'Stock Splits' column)
            if 'Stock Splits' in actions.columns:
                stock_splits = actions[actions['Stock Splits'] != 0]
                if not stock_splits.empty:
                    print(f"\n✓ Stock splits from actions:")
                    print(stock_splits)
    except Exception as e:
        print(f"✗ Error getting actions: {e}")

    # Test adjusted vs unadjusted price data
    try:
        # Get recent historical data
        hist_adj = ticker.history(start="2020-01-01", end="2024-12-31")
        hist_unadj = ticker.history(start="2020-01-01", end="2024-12-31", auto_adjust=False)

        if not hist_adj.empty and not hist_unadj.empty:
            # Compare first and last prices
            first_date = hist_adj.index[0].strftime('%Y-%m-%d')
            first_adj = hist_adj.iloc[0]['Close']
            first_unadj = hist_unadj.iloc[0]['Close']

            print(f"\n✓ Price comparison on {first_date}:")
            print(f"  Adjusted: ${first_adj:.2f}")
            print(f"  Unadjusted: ${first_unadj:.2f}")
            print(f"  Ratio: {first_unadj / first_adj:.4f}")
    except Exception as e:
        print(f"✗ Error comparing prices: {e}")

print("\n" + "="*60)
print("Test complete!")
print("="*60)
