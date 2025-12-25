# ABOUTME: Creates PostgreSQL template database for E2E tests
# ABOUTME: Initializes schema and populates with 51 diverse test stocks from production

import sys
import os
import psycopg

# Add parent directory to path to import Database class
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Database

# Database connection parameters
DB_PARAMS = {
    'host': 'localhost',
    'port': 5432,
    'user': 'lynch',
    'password': 'lynch_dev_password'
}

# Database names
PROD_DB = 'lynch_stocks'
TEMPLATE_DB = 'lynch_stocks_template'

# 37 test stocks selected for diversity across sectors, market caps, and quality scores
TEST_STOCKS = [
    # Technology (15)
    'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMD', 'CRM', 'ADBE', 'ORCL', 'INTC',
    'CSCO', 'QCOM', 'TXN', 'AVGO', 'MU', 'AMAT',
    # Healthcare (8)
    'JNJ', 'UNH', 'PFE', 'ABBV', 'TMO', 'LLY', 'MRK', 'ABT',
    # Finance (8)
    'JPM', 'BAC', 'V', 'MA', 'GS', 'MS', 'C', 'WFC',
    # Consumer Cyclical (6)
    'AMZN', 'TSLA', 'HD', 'NKE', 'MCD', 'SBUX',
    # Industrials (5)
    'BA', 'CAT', 'HON', 'UPS', 'RTX',
    # Energy (4)
    'XOM', 'CVX', 'COP', 'SLB',
    # Consumer Defensive (5)
    'PG', 'KO', 'WMT', 'COST', 'PEP'
]

# Tables to copy data from (in dependency order)
# Tables that filter by symbol
TABLES_TO_COPY = [
    'stocks',
    'stock_metrics',
    'earnings_history',
    'price_history',
    'lynch_analyses',
    'chart_analyses',
    'sec_filings',
    'filing_sections',
    'backtest_results',
    'news_articles',
    'material_events',
    'conversations',
    'messages',
    'message_sources',
    'screening_sessions',  # Required for stock list page
    'screening_results',   # Required for stock list page - contains evaluated stocks
]

# Tables that don't have a symbol column - copy ALL rows
# These are needed for foreign key constraints
TABLES_COPY_ALL = [
    'users',  # Referenced by lynch_analyses, watchlist, etc.
]


def drop_existing_template(conn):
    """Drop existing template database if it exists."""
    print("[1/5] Dropping existing template database...")
    cursor = conn.cursor()

    # Terminate connections to template
    cursor.execute(f"""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = '{TEMPLATE_DB}'
          AND pid <> pg_backend_pid()
    """)

    # Unmark as template (if exists) so we can drop it
    cursor.execute(f"""
        SELECT 1 FROM pg_database WHERE datname = '{TEMPLATE_DB}'
    """)
    if cursor.fetchone():
        cursor.execute(f"ALTER DATABASE {TEMPLATE_DB} IS_TEMPLATE = FALSE")

    cursor.execute(f"DROP DATABASE IF EXISTS {TEMPLATE_DB}")
    cursor.close()
    print("   ✓ Existing template dropped (if any)")


def create_fresh_template(conn):
    """Create fresh template database."""
    print("[2/5] Creating fresh template database...")
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE {TEMPLATE_DB}")
    cursor.close()
    print(f"   ✓ Database created: {TEMPLATE_DB}")


def initialize_schema():
    """Initialize schema in template database by copying from production."""
    print("[3/5] Initializing schema in template database...")
    import subprocess

    # Use pg_dump to copy schema (structure only, no data) from production
    dump_cmd = [
        'pg_dump',
        '-h', str(DB_PARAMS['host']),
        '-p', str(DB_PARAMS['port']),
        '-U', DB_PARAMS['user'],
        '-d', PROD_DB,
        '--schema-only',  # Only structure, no data
        '--no-owner',      # Don't include owner
        '--no-privileges'  # Don't include privileges
    ]

    restore_cmd = [
        'psql',
        '-h', str(DB_PARAMS['host']),
        '-p', str(DB_PARAMS['port']),
        '-U', DB_PARAMS['user'],
        '-d', TEMPLATE_DB,
        '-q'  # Quiet mode
    ]

    # Set password environment variable
    import os
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_PARAMS['password']

    # Dump schema and pipe to restore
    try:
        dump_process = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        restore_process = subprocess.Popen(restore_cmd, stdin=dump_process.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        dump_process.stdout.close()  # Allow dump_process to receive SIGPIPE
        stdout, stderr = restore_process.communicate()

        if restore_process.returncode != 0:
            error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
            # Filter out harmless warnings
            if 'ERROR' in error_msg:
                raise Exception(f"Schema copy failed: {error_msg}")

        print("   ✓ Schema initialized successfully (20+ tables)")

    except FileNotFoundError:
        # pg_dump/psql not found, fall back to Database class
        print("   ⚠ pg_dump not found, using fallback method...")
        db = Database(
            host=DB_PARAMS['host'],
            port=DB_PARAMS['port'],
            database=TEMPLATE_DB,
            user=DB_PARAMS['user'],
            password=DB_PARAMS['password']
        )
        db.flush()
        import time

        # Wait for schema to be fully created - check for stocks table
        template_conn = psycopg.connect(dbname=TEMPLATE_DB, **DB_PARAMS)
        template_cursor = template_conn.cursor()

        max_retries = 30
        for i in range(max_retries):
            try:
                template_cursor.execute("SELECT 1 FROM stocks LIMIT 1")
                # Table exists!
                break
            except psycopg.errors.UndefinedTable:
                if i == max_retries - 1:
                    raise Exception("Schema initialization timed out - stocks table not created")
                time.sleep(1)
                template_conn.rollback()

        template_cursor.close()
        template_conn.close()
        print("   ✓ Schema initialized successfully")


def copy_test_data():
    """Copy test stock data from production to template database."""
    print("[4/5] Copying test data from production...")

    # Connect to both databases
    prod_conn = psycopg.connect(
        dbname=PROD_DB,
        **DB_PARAMS
    )
    template_conn = psycopg.connect(
        dbname=TEMPLATE_DB,
        **DB_PARAMS
    )

    prod_cursor = prod_conn.cursor()
    template_cursor = template_conn.cursor()

    total_rows_copied = 0

    # First, copy tables that don't filter by symbol (ALL rows)
    # These need to be copied first for foreign key constraints
    for table in TABLES_COPY_ALL:
        prod_cursor.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in prod_cursor.fetchall()]
        if not columns:
            continue  # Table doesn't exist
            
        column_list = ', '.join(columns)
        
        # Copy ALL rows from this table
        prod_cursor.execute(f"SELECT {column_list} FROM {table}")
        rows = prod_cursor.fetchall()
        
        if rows:
            BATCH_SIZE = 100
            placeholders = ', '.join(['%s'] * len(columns))
            
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                template_cursor.execute(f"""
                    INSERT INTO {table} ({column_list})
                    VALUES {', '.join([f'({placeholders})' for _ in batch])}
                    ON CONFLICT DO NOTHING
                """, [item for row in batch for item in row])
            
            template_conn.commit()
            print(f"   {table}: {len(rows)} rows (all users)")
            total_rows_copied += len(rows)
            
            # Reset the sequence for the id column to avoid conflicts with new inserts
            if table == 'users':
                template_cursor.execute("""
                    SELECT setval('users_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM users), false)
                """)
                template_conn.commit()
                print(f"   {table}: sequence reset")

    # Now copy symbol-filtered tables

    for table in TABLES_TO_COPY:
        # Skip screening tables - handled specially below
        if table in ('screening_sessions', 'screening_results'):
            continue
            
        # Check if table has a symbol column
        prod_cursor.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table}'
              AND column_name = 'symbol'
        """)

        if not prod_cursor.fetchone():
            # Table doesn't have symbol column, skip it
            continue

        # Get column names for this table
        prod_cursor.execute(f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in prod_cursor.fetchall()]
        column_list = ', '.join(columns)

        # Copy rows for test stocks
        prod_cursor.execute(f"""
            SELECT {column_list}
            FROM {table}
            WHERE symbol = ANY(%s)
        """, (TEST_STOCKS,))

        rows = prod_cursor.fetchall()

        if rows:
            # Insert rows in batches to avoid exceeding PostgreSQL parameter limit (65535)
            BATCH_SIZE = 100
            placeholders = ', '.join(['%s'] * len(columns))
            
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                template_cursor.execute(f"""
                    INSERT INTO {table} ({column_list})
                    VALUES {', '.join([f'({placeholders})' for _ in batch])}
                    ON CONFLICT DO NOTHING
                """, [item for row in batch for item in row])

            template_conn.commit()
            print(f"   {table}: {len(rows)} rows")
            total_rows_copied += len(rows)

    # Special handling for screening_sessions and screening_results
    # Copy the most recent screening session and its results for test stocks
    print("   Copying screening session and results...")
    
    # Get the most recent session
    prod_cursor.execute("""
        SELECT id, created_at, algorithm, status, processed_count, total_count,
               current_symbol, total_analyzed, pass_count, close_count, fail_count
        FROM screening_sessions
        ORDER BY created_at DESC
        LIMIT 1
    """)
    session_row = prod_cursor.fetchone()
    
    if session_row:
        old_session_id = session_row[0]
        
        # Insert the session with a new ID (let it auto-increment)
        template_cursor.execute("""
            INSERT INTO screening_sessions 
            (created_at, algorithm, status, processed_count, total_count,
             current_symbol, total_analyzed, pass_count, close_count, fail_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, session_row[1:])
        new_session_id = template_cursor.fetchone()[0]
        template_conn.commit()
        print(f"   screening_sessions: 1 row (session_id={new_session_id})")
        
        # Get column names for screening_results
        prod_cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'screening_results'
            ORDER BY ordinal_position
        """)
        result_columns = [row[0] for row in prod_cursor.fetchall()]
        
        # Copy screening results for test stocks, replacing session_id
        prod_cursor.execute(f"""
            SELECT {', '.join(result_columns)}
            FROM screening_results
            WHERE session_id = %s AND symbol = ANY(%s)
        """, (old_session_id, TEST_STOCKS))
        
        result_rows = prod_cursor.fetchall()
        
        if result_rows:
            # Find the index of session_id and id columns
            session_id_idx = result_columns.index('session_id') if 'session_id' in result_columns else None
            id_idx = result_columns.index('id') if 'id' in result_columns else None
            
            # Build column list without 'id' (let it auto-increment)
            insert_columns = [c for c in result_columns if c != 'id']
            
            for row in result_rows:
                row_list = list(row)
                # Replace old session_id with new session_id
                if session_id_idx is not None:
                    row_list[session_id_idx] = new_session_id
                # Remove 'id' value if present
                if id_idx is not None:
                    row_list.pop(id_idx)
                
                placeholders = ', '.join(['%s'] * len(insert_columns))
                template_cursor.execute(f"""
                    INSERT INTO screening_results ({', '.join(insert_columns)})
                    VALUES ({placeholders})
                    ON CONFLICT DO NOTHING
                """, row_list)
            
            template_conn.commit()
            print(f"   screening_results: {len(result_rows)} rows")
            total_rows_copied += len(result_rows) + 1

    prod_cursor.close()
    template_cursor.close()
    prod_conn.close()
    template_conn.close()

    print(f"   ✓ Total rows copied: {total_rows_copied}")


def mark_as_template(conn):
    """Mark database as template (read-only)."""
    print("[5/5] Marking as template database...")
    cursor = conn.cursor()
    cursor.execute(f"ALTER DATABASE {TEMPLATE_DB} IS_TEMPLATE = TRUE")
    cursor.close()
    print("   ✓ Database marked as template")


def create_template_database():
    """Main function to create template database."""
    print("=" * 60)
    print("Creating Test Database Template")
    print("=" * 60)
    print()

    # Connect to postgres database for admin operations
    conn = psycopg.connect(dbname='postgres', autocommit=True, **DB_PARAMS)

    try:
        # Step 1: Drop existing template
        drop_existing_template(conn)

        # Step 2: Create fresh template
        create_fresh_template(conn)

        # Step 3: Initialize schema
        initialize_schema()

        # Step 4: Copy test data
        copy_test_data()

        # Step 5: Mark as template
        mark_as_template(conn)

        print()
        print("=" * 60)
        print(f"✓ Template database created: {TEMPLATE_DB}")
        print(f"  - Stocks: {len(TEST_STOCKS)}")
        print(f"  - Ready for E2E tests")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Error creating template database: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    create_template_database()
