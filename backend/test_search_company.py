from dotenv import load_dotenv
load_dotenv()
from database import Database
from stock_context import StockContext
from agent_tools import ToolExecutor

db = Database()
stock_ctx = StockContext(db)
executor = ToolExecutor(db, stock_context=stock_ctx)

print("=== Testing search_company ===")

# Test 1: Exact match
print("\n1. Search for 'Figma':")
result = executor.execute("search_company", {"company_name": "Figma"})
if "error" in result:
    print(f"  Error: {result['error']}")
else:
    print(f"  Found {result['count']} matches:")
    for match in result["matches"]:
        print(f"    {match['ticker']}: {match['company_name']} ({match['sector']})")

# Test 2: Partial match
print("\n2. Search for 'Apple':")
result = executor.execute("search_company", {"company_name": "Apple"})
if "error" in result:
    print(f"  Error: {result['error']}")
else:
    print(f"  Found {result['count']} matches:")
    for match in result["matches"]:
        print(f"    {match['ticker']}: {match['company_name']} ({match['sector']})")

# Test 3: Case insensitive
print("\n3. Search for 'microsoft' (lowercase):")
result = executor.execute("search_company", {"company_name": "microsoft"})
if "error" in result:
    print(f"  Error: {result['error']}")
else:
    print(f"  Found {result['count']} matches:")
    for match in result["matches"]:
        print(f"    {match['ticker']}: {match['company_name']} ({match['sector']})")

# Test 4: No match
print("\n4. Search for 'XYZ123NotACompany':")
result = executor.execute("search_company", {"company_name": "XYZ123NotACompany"})
if "error" in result:
    print(f"  Error: {result['error']}")
    print(f"  Suggestion: {result.get('suggestion')}")
else:
    print(f"  Found {result['count']} matches")
