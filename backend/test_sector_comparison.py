import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from database import Database
from agent_tools import ToolExecutor
import json

def test_sector_comparison():
    print("Initializing Database...")
    db = Database()
    executor = ToolExecutor(db)
    
    ticker = "AAPL"
    print(f"\nTesting get_sector_comparison for {ticker}...")
    
    result = executor.execute("get_sector_comparison", {"ticker": ticker})
    
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print("\n" + "="*50)
    print(f"SECTOR ANALYSIS: {result.get('company_name')} ({result.get('ticker')})")
    print(f"Sector: {result.get('sector')}")
    print(f"Peers Analyzed: {result.get('peer_count')}")
    print("="*50)
    
    comparison = result.get("comparison", {})
    
    metrics = [
        ("P/E Ratio", "pe_ratio"),
        ("PEG Ratio", "peg_ratio"),
        ("Div Yield", "dividend_yield"),
        ("Rev Growth", "revenue_growth"),
        ("EPS Growth", "eps_growth"),
        ("Debt/Equity", "debt_to_equity")
    ]
    
    print(f"{'Metric':<15} | {'Stock':<10} | {'Sector Avg':<10} | {'Diff %':<10}")
    print("-" * 55)
    
    for label, key in metrics:
        data = comparison.get(key, {})
        stock_val = data.get("stock")
        sector_val = data.get("sector_avg")
        
        # Format values
        stock_str = str(stock_val) if stock_val is not None else "-"
        sector_str = str(sector_val) if sector_val is not None else "-"
        
        diff_str = "-"
        if stock_val is not None and sector_val is not None and sector_val != 0:
            diff = ((stock_val - sector_val) / abs(sector_val)) * 100
            diff_str = f"{diff:+.1f}%"
            
        print(f"{label:<15} | {stock_str:<10} | {sector_str:<10} | {diff_str:<10}")

if __name__ == "__main__":
    test_sector_comparison()
