"""
Shared pytest fixtures for all test suites.
"""
import pytest
import psycopg
import sys
import os

# Add backend directory to Python path for all test imports
# This must happen at module level, before any test collection,
# to avoid import conflicts when pytest collects from multiple directories
backend_path = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, os.path.abspath(backend_path))


@pytest.fixture(scope="session", autouse=True)
def configure_test_environment():
    """Configure environment variables for all tests."""
    # Use smaller connection pool for tests to avoid exceeding PostgreSQL max_connections
    os.environ['DB_POOL_SIZE'] = '10'
    yield
    # Cleanup if needed


def _ensure_template_exists(cursor, template_db):
    """
    Ensure the test template database exists.
    If it doesn't exist, automatically create it from production data.
    """
    cursor.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s AND datistemplate = TRUE",
        (template_db,)
    )
    
    if cursor.fetchone():
        print(f"[TEST DB] Template '{template_db}' found")
        return True
    
    print(f"[TEST DB] Template '{template_db}' not found - creating automatically...")
    
    # Import and run the template creation script
    try:
        # Add tests/backend to path temporarily for the import
        tests_backend_path = os.path.join(os.path.dirname(__file__), 'backend')
        sys.path.insert(0, tests_backend_path)
        
        from create_test_template import create_template_database
        create_template_database()
        
        # Remove from path
        sys.path.remove(tests_backend_path)
        
        print(f"[TEST DB] ✓ Template created successfully")
        return True
        
    except Exception as e:
        print(f"[TEST DB] ✗ Failed to create template: {e}")
        raise Exception(
            f"Failed to auto-create template database '{template_db}'.\n"
            f"Error: {e}\n"
            f"You can try manually: python tests/backend/create_test_template.py"
        )


@pytest.fixture(scope="session")
def test_database():
    """Create test database from template for test session, drop after completion."""
    TEMPLATE_DB = 'lynch_stocks_template'
    TEST_DB = 'lynch_stocks_test'

    print("\n[TEST DB] Setting up test database...")

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

    # Ensure template exists (auto-creates if missing)
    _ensure_template_exists(cursor, TEMPLATE_DB)

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
