#!/usr/bin/env python3
# ABOUTME: Creates test template database in CI from SQL dump
# ABOUTME: Restores schema and data without requiring production database

"""
Creates template database for CI environment by restoring from SQL dump.
Unlike create_test_template.py, this doesn't copy from production.
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
import subprocess

def create_template_from_dump():
    """Create template database from SQL dump file."""

    # Database connection params
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = int(os.environ.get('DB_PORT', 5432))
    db_user = os.environ.get('DB_USER', 'lynch')
    db_password = os.environ.get('DB_PASSWORD', 'lynch_dev_password')

    print("[1/3] Creating empty template database...")

    # Connect to postgres database for admin operations
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database='postgres'
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # Terminate connections to template database
    cursor.execute("""
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = 'lynch_stocks_template'
          AND pid <> pg_backend_pid()
    """)

    # Unmark as template if exists (so we can drop it)
    cursor.execute("""
        SELECT 1 FROM pg_database WHERE datname = 'lynch_stocks_template'
    """)
    if cursor.fetchone():
        cursor.execute("ALTER DATABASE lynch_stocks_template IS_TEMPLATE = FALSE")

    # Create template database (drop first if exists)
    cursor.execute("DROP DATABASE IF EXISTS lynch_stocks_template")
    cursor.execute("CREATE DATABASE lynch_stocks_template")

    cursor.close()
    conn.close()

    print("   ✓ Empty template database created")

    print("[2/3] Restoring schema and data from SQL dump...")

    # Restore from SQL dump using psql
    dump_path = os.path.join(
        os.path.dirname(__file__),
        'fixtures',
        'template_dump.sql'
    )

    restore_cmd = [
        'psql',
        '-h', db_host,
        '-p', str(db_port),
        '-U', db_user,
        '-d', 'lynch_stocks_template',
        '-f', dump_path,
        '-q'  # Quiet mode
    ]

    env = os.environ.copy()
    env['PGPASSWORD'] = db_password

    result = subprocess.run(
        restore_cmd,
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        # Check if error is serious (filter out warnings)
        if 'ERROR' in result.stderr:
            raise Exception(f"SQL restore failed: {result.stderr}")

    print("   ✓ Schema and data restored successfully")

    print("[3/3] Marking as template database...")

    # Mark as template
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database='postgres'
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    cursor.execute("ALTER DATABASE lynch_stocks_template IS_TEMPLATE = TRUE")

    cursor.close()
    conn.close()

    print("   ✓ Database marked as template")
    print("\n✓ Template database created successfully for CI")

if __name__ == '__main__':
    try:
        create_template_from_dump()
    except Exception as e:
        print(f"\n✗ Error creating template: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
