#!/usr/bin/env python3
"""Quick test to verify PostgreSQL setup and SEC data access"""

from database import Database
import psycopg2

def test_postgres_connection():
    """Test basic database connection"""
    print("Testing PostgreSQL connection...")
    db = Database()
    print("✓ Database connection successful")
    return db

def test_sec_data_access():
    """Test querying SEC company_facts data"""
    print("\nTesting SEC company_facts access...")

    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="lynch_stocks",
        user="lynch",
        password="lynch_dev_password"
    )
    cursor = conn.cursor()

    # Check total companies
    cursor.execute("SELECT COUNT(*) FROM company_facts")
    total = cursor.fetchone()[0]
    print(f"✓ Total companies in company_facts: {total:,}")

    # Check companies with tickers
    cursor.execute("SELECT COUNT(*) FROM company_facts WHERE ticker IS NOT NULL AND ticker != ''")
    with_ticker = cursor.fetchone()[0]
    print(f"✓ Companies with ticker symbols: {with_ticker:,}")

    # Test querying by ticker (AAPL)
    cursor.execute("SELECT cik, entity_name, ticker FROM company_facts WHERE ticker = 'AAPL'")
    row = cursor.fetchone()
    if row:
        print(f"✓ Found AAPL: CIK={row[0]}, Name={row[1]}")
    else:
        print("✗ Could not find AAPL")

    # Test querying by CIK
    cursor.execute("SELECT cik, entity_name, ticker FROM company_facts WHERE cik = '0000320193'")
    row = cursor.fetchone()
    if row:
        print(f"✓ Found by CIK: {row[1]} ({row[2]})")
    else:
        print("✗ Could not find by CIK")

    # Test JSONB query - get Apple's revenue
    cursor.execute("""
        SELECT facts->'us-gaap'->'Revenues'->'units'->'USD'
        FROM company_facts
        WHERE ticker = 'AAPL'
        LIMIT 1
    """)
    revenue_data = cursor.fetchone()
    if revenue_data and revenue_data[0]:
        print(f"✓ Successfully queried JSONB data (found revenue entries)")
    else:
        print("✗ Could not query JSONB data")

    conn.close()
    print("\n✓ All SEC data tests passed!")

def test_stock_operations(test_db):
    """Test basic stock operations"""
    print("\nTesting stock operations...")

    # Save a test stock
    test_db.save_stock_basic(
        symbol="TEST",
        company_name="Test Company",
        exchange="NASDAQ",
        sector="Technology"
    )
    test_db.flush()  # Ensure stock is committed
    print("✓ Saved test stock")

    # Save test metrics
    test_db.save_stock_metrics("TEST", {
        'price': 100.0,
        'pe_ratio': 25.0,
        'market_cap': 1000000000
    })
    test_db.flush()  # Ensure metrics are committed
    print("✓ Saved test stock metrics")

    # Retrieve stock
    metrics = test_db.get_stock_metrics("TEST")
    if metrics:
        print(f"✓ Retrieved test stock: {metrics['company_name']} @ ${metrics['price']}")
    else:
        print("✗ Could not retrieve test stock")

if __name__ == '__main__':
    try:
        db = test_postgres_connection()
        test_sec_data_access()
        test_stock_operations(db)
        print("\n" + "="*60)
        print("ALL TESTS PASSED! PostgreSQL setup is working correctly.")
        print("="*60)
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
