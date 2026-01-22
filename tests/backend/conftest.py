# ABOUTME: Pytest fixtures for tests/backend directory
# ABOUTME: Provides test_database fixture for PostgreSQL test database setup

import pytest
import psycopg
import sys
import os

# Add backend directory to Python path for all test imports
# Add backend directory to Python path for all test imports
# Note: Root tests/conftest.py also adds this, but we keep it here to support 
# running tests specifically from this directory if needed
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
if os.path.abspath(backend_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(backend_path))


@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """Configure environment variables for all tests."""
    import os
    # Use smaller connection pool for tests to avoid exceeding PostgreSQL max_connections
    os.environ['DB_POOL_SIZE'] = '10'
    yield


@pytest.fixture(scope="session")
def test_database():
    """Create empty test database with schema only (no template data) for unit tests."""
    TEST_DB = 'lynch_stocks_backend_test'

    print("\n[BACKEND TEST DB] Setting up empty test database for unit tests...")

    # Connect to postgres database for admin operations
    conn = psycopg.connect(
        dbname='postgres',
        user='lynch',
        password='lynch_dev_password',
        host='localhost',
        port=5432,
        autocommit=True
    )
    cursor = conn.cursor()

    # Terminate any existing connections to test database
    cursor.execute(f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{TEST_DB}'
          AND pid <> pg_backend_pid()
    """)

    # Drop existing test database if it exists
    cursor.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")

    # Create empty test database (no template - schema will be created by Database class)
    print(f"[BACKEND TEST DB] Creating empty test database...")
    cursor.execute(f"CREATE DATABASE {TEST_DB}")
    print(f"[BACKEND TEST DB] ✓ Empty test database created: {TEST_DB}")
    print(f"[BACKEND TEST DB] Schema will be initialized by Database class")

    cursor.close()
    conn.close()

    yield TEST_DB

    # Cleanup: Drop test database
    print(f"\n[BACKEND TEST DB] Cleaning up test database...")

    conn = psycopg.connect(
        dbname='postgres',
        user='lynch',
        password='lynch_dev_password',
        host='localhost',
        port=5432,
        autocommit=True
    )
    cursor = conn.cursor()

    # Terminate all connections to test database
    cursor.execute(f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{TEST_DB}'
          AND pid <> pg_backend_pid()
    """)

    # Drop test database
    cursor.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    print(f"[BACKEND TEST DB] ✓ Test database dropped")

    cursor.close()
    conn.close()


@pytest.fixture(scope="session")
def shared_db(test_database):
    """Session-scoped Database instance shared across all tests.

    Creates a single Database instance to avoid connection pool exhaustion.
    """
    import sys
    import os

    # Add backend directory to path for imports
    backend_path = os.path.join(os.path.dirname(__file__), '..')
    sys.path.insert(0, os.path.abspath(backend_path))

    from database import Database

    db = Database(
        host='localhost',
        port=5432,
        database=test_database,
        user='lynch',
        password='lynch_dev_password'
    )

    yield db

    # No cleanup needed - session ends


@pytest.fixture
def test_db(shared_db):
    """Function-scoped fixture that cleans up test data before/after each test.

    Uses the shared Database instance but ensures clean state for each test.
    """
    db = shared_db

    # Flush async write queue before cleaning tables
    db.flush()

    # Clean up test data before each test
    conn = db.get_connection()
    cursor = conn.cursor()

    # Clear all data - try each table individually to handle tables that may not exist
    # Order matters: delete from child tables before parent tables (due to foreign keys)
    tables_to_clear = [
        # Child tables first (foreign key dependencies)
        'message_sources', 'messages', 'conversations',
        'watchlist', 'weekly_prices', 'stock_metrics', 'earnings_history',
        'lynch_analyses', 'chart_analyses', 'news_articles', 'material_events',
        'filing_sections', 'sec_filings', 'screening_results',
        'insider_trades', 'dcf_recommendations', 'backtest_results',
        'optimization_runs', 'algorithm_configurations',
        # Paper trading tables
        'portfolio_value_snapshots', 'portfolio_transactions', 'portfolios',
        # Parent tables last
        'screening_sessions', 'background_jobs', 'app_settings',
        'stocks', 'users'
    ]

    for table in tables_to_clear:
        try:
            cursor.execute(f'DELETE FROM {table}')
        except Exception:
            # Table doesn't exist yet, skip
            pass

    conn.commit()
    cursor.close()
    db.return_connection(conn)

    yield db

    # Flush async write queue before cleaning tables
    db.flush()

    # Cleanup after test
    conn = db.get_connection()
    cursor = conn.cursor()

    for table in tables_to_clear:
        try:
            cursor.execute(f'DELETE FROM {table}')
        except Exception:
            # Table doesn't exist, skip
            pass

    conn.commit()
    cursor.close()
    db.return_connection(conn)


@pytest.fixture(scope="function")
def test_client(test_database):
    """Create Flask test client with test database.

    Note: test_database fixture is defined above.
    """
    import os
    import sys

    # Set test database environment variables BEFORE importing app
    os.environ['DB_NAME'] = test_database
    os.environ['DB_HOST'] = 'localhost'
    os.environ['DB_PORT'] = '5432'
    os.environ['DB_USER'] = 'lynch'
    os.environ['DB_PASSWORD'] = 'lynch_dev_password'

    # Add backend directory to path for imports
    backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
    sys.path.insert(0, os.path.abspath(backend_path))

    # Import app AFTER setting env vars
    from app import app
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client


@pytest.fixture(scope="function")
def mock_yfinance():
    """Mock yfinance to avoid external API calls in tests."""
    import unittest.mock as mock

    with mock.patch('yfinance.Ticker') as mock_ticker:
        # Create a mock ticker instance with realistic data
        mock_instance = mock.MagicMock()

        # Mock info property with realistic stock data
        mock_instance.info = {
            'symbol': 'AAPL',
            'shortName': 'Apple Inc.',
            'country': 'United States',
            'marketCap': 3000000000000,
            'price': 180.00,
            'currentPrice': 180.00,
            'trailingPE': 30.0,
            'forwardPE': 28.0,
            'debtToEquity': 150.0,
            'trailingEps': 6.00
        }

        # Mock fast_info property
        mock_fast_info = mock.MagicMock()
        mock_fast_info.last_price = 180.00
        mock_fast_info.market_cap = 3000000000000
        mock_instance.fast_info = mock_fast_info

        mock_ticker.return_value = mock_instance
        yield mock_ticker


def pytest_collection_modifyitems(items):
    """Automatically add 'backend' marker to all tests in this directory."""
    for item in items:
        if "tests/backend" in str(item.fspath):
            item.add_marker(pytest.mark.backend)
