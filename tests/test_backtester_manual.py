import sys
import os
import logging

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../backend'))

from database import Database
from backtester import Backtester

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_googl_backtest():
    print("Initializing Database...")
    db = Database()
    backtester = Backtester(db)
    
    symbol = 'GOOGL'
    years_back = 1
    
    print(f"Running backtest for {symbol} ({years_back} year ago)...")
    
    # Debug: Check if price history exists
    start_date_str = "2024-11-29"
    history = db.get_price_history(symbol, start_date="2024-11-01", end_date="2024-12-01")
    print(f"Debug: Found {len(history)} price points in Nov 2024")
    if history:
        print(f"Sample: {history[0]}")
        
    result = backtester.run_backtest(symbol, years_back)
    
    if 'error' in result:
        print(f"Error: {result['error']}")
    else:
        print("\n=== Backtest Results ===")
        print(f"Symbol: {result['symbol']}")
        print(f"Date: {result['backtest_date']}")
        print(f"Start Price: ${result['start_price']:.2f}")
        print(f"End Price: ${result['end_price']:.2f}")
        print(f"Total Return: {result['total_return']:.2f}%")
        print(f"Historical Score: {result['historical_score']}")
        print(f"Historical Rating: {result['historical_rating']}")
        print("\nHistorical Data Snapshot:")
        for key, value in result['historical_data'].items():
            if key not in ['metrics', 'breakdown']:
                print(f"  {key}: {value}")

if __name__ == "__main__":
    test_googl_backtest()
