from dotenv import load_dotenv
load_dotenv()
from database import Database
from rag_context import RAGContext
from agent_tools import ToolExecutor

db = Database()
rag = RAGContext(db)
executor = ToolExecutor(db, rag_context=rag)

# Test get_dividend_analysis with Coca-Cola (known dividend aristocrat)
print("=== Testing get_dividend_analysis (KO) ===")
result = executor.execute("get_dividend_analysis", {"ticker": "KO", "years": 5})
if "error" in result:
    print("Error:", result)
else:
    print(f"Current Yield: {result['current_yield_pct']}%")
    print(f"Years of data: {result['years_of_data']}")
    print("\nDividend History:")
    for div in result["dividend_history"]:
        print(f"  {div['year']}: ${div['dividend_per_share']}, Payout={div['payout_ratio_pct']}%")
    print("\nDividend Growth:")
    for period, data in result["dividend_growth"].items():
        print(f"  {period}: {data['cagr_pct']}% CAGR ({data['start_year']}-{data['end_year']})")

print("\n=== Testing with non-dividend stock (TSLA) ===")
result = executor.execute("get_dividend_analysis", {"ticker": "TSLA"})
print(result.get("message", result.get("error")))
