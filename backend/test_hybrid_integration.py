# ABOUTME: Integration test script for hybrid EDGAR + yfinance data fetcher
# ABOUTME: Verifies real-world data fetching and displays comparison of data sources

from database import Database
from data_fetcher import DataFetcher
from lynch_criteria import LynchCriteria
from earnings_analyzer import EarningsAnalyzer
import os

def test_hybrid_fetch():
    """Test hybrid data fetching with a real stock"""

    # Clean up test database if it exists
    test_db_path = "test_hybrid.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # Initialize components
    db = Database(test_db_path)
    fetcher = DataFetcher(db)
    analyzer = EarningsAnalyzer(db)
    criteria = LynchCriteria(db, analyzer)

    print("\n" + "="*80)
    print("Testing Hybrid EDGAR + yfinance Data Fetcher")
    print("="*80)

    # Test with Apple (AAPL)
    symbol = "AAPL"
    print(f"\nFetching data for {symbol}...")
    print("-" * 80)

    # Fetch stock data (will use hybrid approach)
    stock_data = fetcher.fetch_stock_data(symbol, force_refresh=True)

    if not stock_data:
        print(f"❌ Failed to fetch data for {symbol}")
        return

    print(f"✅ Successfully fetched data for {symbol}")
    print(f"\nStock Metrics from yfinance:")
    print(f"  - Price: ${stock_data.get('price', 'N/A')}")
    print(f"  - P/E Ratio: {stock_data.get('pe_ratio', 'N/A')}")
    print(f"  - Market Cap: ${stock_data.get('market_cap', 'N/A'):,.0f}" if stock_data.get('market_cap') else "  - Market Cap: N/A")
    print(f"  - Institutional Ownership: {stock_data.get('institutional_ownership', 'N/A')}")

    print(f"\nFundamental Metrics (from EDGAR or yfinance fallback):")
    print(f"  - Debt-to-Equity: {stock_data.get('debt_to_equity', 'N/A')}")

    # Get earnings history
    earnings_history = db.get_earnings_history(symbol)
    print(f"\nEarnings History ({len(earnings_history)} years):")
    for entry in sorted(earnings_history, key=lambda x: x['year'], reverse=True)[:5]:
        print(f"  - {entry['year']}: EPS = ${entry['eps']:.2f}, Revenue = ${entry['revenue']:,.0f}")

    # Evaluate against Lynch criteria
    evaluation = criteria.evaluate_stock(symbol)

    if evaluation:
        print(f"\nLynch Criteria Evaluation:")
        print(f"  - PEG Ratio: {evaluation.get('peg_ratio', 'N/A'):.2f}" if evaluation.get('peg_ratio') else "  - PEG Ratio: N/A")
        print(f"  - 5Y EPS Growth (CAGR): {evaluation.get('earnings_cagr', 'N/A'):.1f}%" if evaluation.get('earnings_cagr') else "  - 5Y EPS Growth: N/A")
        print(f"  - 5Y Revenue Growth (CAGR): {evaluation.get('revenue_cagr', 'N/A'):.1f}%" if evaluation.get('revenue_cagr') else "  - 5Y Revenue Growth: N/A")
        print(f"  - Consistency Score: {evaluation.get('consistency_score', 'N/A'):.2f}" if evaluation.get('consistency_score') else "  - Consistency Score: N/A")
        print(f"\n  Status Summary:")
        print(f"    • PEG: {evaluation.get('peg_status', 'N/A')}")
        print(f"    • Debt: {evaluation.get('debt_status', 'N/A')}")
        print(f"    • Institutional Ownership: {evaluation.get('institutional_ownership_status', 'N/A')}")
        print(f"    • Overall: {evaluation.get('overall_status', 'N/A')}")

    print("\n" + "="*80)
    print("✅ Hybrid integration test completed successfully!")
    print("="*80 + "\n")

    # Clean up
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

if __name__ == "__main__":
    test_hybrid_fetch()
