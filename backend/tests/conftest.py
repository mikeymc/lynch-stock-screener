# ABOUTME: Pytest fixtures for backend/tests directory
# ABOUTME: Provides test_database fixture for PostgreSQL test database setup

import pytest
import psycopg2


@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """Configure environment variables for all tests."""
    import os
    # Use smaller connection pool for tests to avoid exceeding PostgreSQL max_connections
    os.environ['DB_POOL_SIZE'] = '10'
    yield


@pytest.fixture(scope="session")
def test_database():
    """Create test database from template for test session, drop after completion."""
    TEMPLATE_DB = 'lynch_stocks_template'
    TEST_DB = 'lynch_stocks_test'

    print("\n[TEST DB] Setting up test database...")

    # Connect to postgres database for admin operations
    conn = psycopg2.connect(
        database='postgres',
        user='lynch',
        password='lynch_dev_password',
        host='localhost',
        port=5432
    )
    conn.autocommit = True
    cursor = conn.cursor()

    # Verify template exists
    cursor.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s AND datistemplate = TRUE",
        (TEMPLATE_DB,)
    )
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        raise Exception(
            f"Template database '{TEMPLATE_DB}' not found.\n"
            f"Run 'python backend/tests/create_test_template.py' first."
        )

    # Terminate any existing connections to test database
    cursor.execute(f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{TEST_DB}'
          AND pid <> pg_backend_pid()
    """)

    # Drop existing test database if it exists
    cursor.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")

    # Create test database from template
    print(f"[TEST DB] Creating test database from template...")
    cursor.execute(f"CREATE DATABASE {TEST_DB} TEMPLATE {TEMPLATE_DB}")
    print(f"[TEST DB] ✓ Test database created: {TEST_DB}")

    yield TEST_DB

    # Cleanup: Drop test database
    print(f"\n[TEST DB] Cleaning up test database...")

    # Terminate all connections to test database
    cursor.execute(f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{TEST_DB}'
          AND pid <> pg_backend_pid()
    """)

    # Drop test database
    cursor.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    print(f"[TEST DB] ✓ Test database dropped")

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

    # Clean up test data before each test
    conn = db.get_connection()
    cursor = conn.cursor()

    # Get template stocks to preserve
    cursor.execute('SELECT DISTINCT symbol FROM screening_results')
    template_symbols = [row[0] for row in cursor.fetchall()]

    if template_symbols:
        template_list = ','.join(["'%s'" % s for s in template_symbols])

        # Clear test-specific data - delete in order respecting foreign keys
        cursor.execute(f'DELETE FROM watchlist WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM price_history WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM stock_metrics WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM earnings_history WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM lynch_analyses WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM chart_analyses WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM conversations WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM news_articles WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM material_events WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM sec_filings WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM filing_sections WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM stocks WHERE symbol NOT IN ({template_list})')

    cursor.execute('DELETE FROM screening_sessions WHERE id > 1')  # Keep session 1 from template

    conn.commit()
    cursor.close()
    db.return_connection(conn)

    yield db

    # Cleanup after test
    conn = db.get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT DISTINCT symbol FROM screening_results')
    template_symbols = [row[0] for row in cursor.fetchall()]

    if template_symbols:
        template_list = ','.join(["'%s'" % s for s in template_symbols])

        cursor.execute(f'DELETE FROM watchlist WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM price_history WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM stock_metrics WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM earnings_history WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM lynch_analyses WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM chart_analyses WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM conversations WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM news_articles WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM material_events WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM sec_filings WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM filing_sections WHERE symbol NOT IN ({template_list})')
        cursor.execute(f'DELETE FROM stocks WHERE symbol NOT IN ({template_list})')

    cursor.execute('DELETE FROM screening_sessions WHERE id > 1')

    conn.commit()
    cursor.close()
    db.return_connection(conn)
