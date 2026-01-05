from dotenv import load_dotenv
load_dotenv()
from database import Database
from rag_context import RAGContext
from agent_tools import ToolExecutor

db = Database()
rag = RAGContext(db)
executor = ToolExecutor(db, rag_context=rag)

print("=== Testing get_analyst_estimates (AAPL) ===")
result = executor.execute("get_analyst_estimates", {"ticker": "AAPL"})
if "error" in result:
    print("Error:", result)
else:
    print(f"Ticker: {result['ticker']}")
    for period, data in result["estimates"].items():
        eps = data["eps"]
        rev = data["revenue"]
        print(f"\n{period}:")
        print(f"  EPS: ${eps['avg']} ({eps['num_analysts']} analysts), Growth: {eps['growth_pct']}%")
        print(f"  Revenue: ${rev['avg_b']}B ({rev['num_analysts']} analysts), Growth: {rev['growth_pct']}%")

print("\n=== Testing compare_stocks (AAPL, MSFT, GOOGL) ===")
result = executor.execute("compare_stocks", {"tickers": ["AAPL", "MSFT", "GOOGL"]})
if "error" in result:
    print("Error:", result)
else:
    print(f"Comparing: {', '.join(result['tickers'])}")
    for ticker, metrics in result["metrics"].items():
        if "error" in metrics:
            print(f"\n{ticker}: {metrics['error']}")
        else:
            print(f"\n{ticker} ({metrics['company_name']}):")
            print(f"  Sector: {metrics['sector']}")
            print(f"  Price: ${metrics['price']}, Market Cap: ${metrics['market_cap_b']}B")
            print(f"  P/E: {metrics['pe_ratio']}, Forward P/E: {metrics['forward_pe']}")
            print(f"  PEG: {metrics['peg_ratio']}, D/E: {metrics['debt_to_equity']}")

print("\n=== Testing find_similar_stocks (NVDA) ===")
result = executor.execute("find_similar_stocks", {"ticker": "NVDA", "limit": 5})
if "error" in result:
    print("Error:", result)
else:
    print(f"Reference: {result['reference_ticker']} ({result['reference_sector']}, ${result['reference_market_cap_b']}B)")
    print(f"Found {result['count']} similar stocks:")
    for stock in result["similar_stocks"]:
        print(f"  {stock['symbol']}: Score={stock['lynch_score']}, PEG={stock['peg_ratio']}, Earnings CAGR={stock['earnings_cagr_pct']}%")
