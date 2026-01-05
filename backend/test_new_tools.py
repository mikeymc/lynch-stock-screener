from dotenv import load_dotenv
load_dotenv()
from database import Database
from rag_context import RAGContext
from agent_tools import ToolExecutor

db = Database()
rag = RAGContext(db)
executor = ToolExecutor(db, rag_context=rag)

# Test get_growth_rates
print("=== Testing get_growth_rates (NVDA) ===")
result = executor.execute("get_growth_rates", {"ticker": "NVDA"})
if "error" in result:
    print("Error:", result)
else:
    print(f"Latest year: {result['latest_year']}")
    print("Revenue Growth:")
    for period, data in result["revenue_growth"].items():
        if data["cagr_pct"]:
            print(f"  {period}: {data['cagr_pct']}% CAGR ({data['start_year']}-{data['end_year']})")
    print("Earnings Growth:")
    for period, data in result["earnings_growth"].items():
        if data["cagr_pct"]:
            print(f"  {period}: {data['cagr_pct']}% CAGR ({data['start_year']}-{data['end_year']})")

print()
# Test get_cash_flow_analysis
print("=== Testing get_cash_flow_analysis (AAPL) ===")
result = executor.execute("get_cash_flow_analysis", {"ticker": "AAPL", "years": 5})
if "error" in result:
    print("Error:", result)
else:
    print(f"Years of data: {result['years_of_data']}")
    for cf in result["cash_flow_trends"]:
        fcf = cf["free_cash_flow_b"]
        margin = cf["fcf_margin_pct"]
        print(f"  {cf['year']}: FCF=${fcf}B, Margin={margin}%")
