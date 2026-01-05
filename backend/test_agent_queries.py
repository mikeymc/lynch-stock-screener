"""
Test if the agent calls tools with different phrasings.
"""
from dotenv import load_dotenv
load_dotenv()
from database import Database
from smart_chat_agent import SmartChatAgent

db = Database()
agent = SmartChatAgent(db)

test_queries = [
    # Direct ticker symbol
    ("What are the analyst estimates for FIG?", "Direct ticker"),
    
    # Company name
    ("Tell me about Figma's revenue growth", "Company name"),
    
    # Comparison with known ticker
    ("Compare FIG to AAPL", "Compare with known ticker"),
    
    # Very explicit
    ("Use get_stock_metrics to look up FIG", "Explicit tool request"),
]

for query, desc in test_queries:
    print(f"\n=== {desc} ===")
    print(f"Query: {query}")
    result = agent.chat("AAPL", query, [])
    print(f"Tool calls: {len(result.get('tool_calls', []))}")
    for call in result.get('tool_calls', []):
        print(f"  - {call['tool']}({call['args']})")
    print(f"Response: {result['response'][:200]}...")
    print("-" * 50)
