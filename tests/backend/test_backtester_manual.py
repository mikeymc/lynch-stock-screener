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
    
    # Debug: Check if weekly price data exists
    start_date_str = "2024-11-29"
    weekly_data = db.get_weekly_prices(symbol)
    if weekly_data and weekly_data.get('dates'):
        print(f"Debug: Found {len(weekly_data['dates'])} weekly price points")
        print(f"Sample: {weekly_data['dates'][0]} - ${weekly_data['prices'][0]:.2f}")
    else:
        print("Debug: No weekly price data found")
        
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
