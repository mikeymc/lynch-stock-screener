# ABOUTME: Migration script to fix earnings_history UNIQUE constraint
# ABOUTME: Changes UNIQUE(symbol, year) to UNIQUE(symbol, year, period) to support quarterly data

import sqlite3
import sys
from datetime import datetime

def migrate_earnings_history(db_path='stocks.db'):
    """
    Migrate earnings_history table to include period in UNIQUE constraint.
    This allows storing both quarterly and annual data for the same year.
    """
    print(f"Starting migration of {db_path}...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if period column exists
        cursor.execute("PRAGMA table_info(earnings_history)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'period' not in columns:
            print("ERROR: period column doesn't exist. Run the app first to add it via normal migration.")
            return False

        # Backup existing data
        print("Backing up existing earnings_history data...")
        cursor.execute("SELECT * FROM earnings_history")
        backup_data = cursor.fetchall()
        print(f"Backed up {len(backup_data)} records")

        # Get column info to preserve data correctly
        cursor.execute("PRAGMA table_info(earnings_history)")
        column_info = cursor.fetchall()
        columns_list = [col[1] for col in column_info]

        # Drop the old table
        print("Dropping old earnings_history table...")
        cursor.execute("DROP TABLE IF EXISTS earnings_history")

        # Create new table with correct UNIQUE constraint
        print("Creating new earnings_history table with UNIQUE(symbol, year, period)...")
        cursor.execute("""
            CREATE TABLE earnings_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                year INTEGER,
                earnings_per_share REAL,
                revenue REAL,
                fiscal_end TEXT,
                last_updated TIMESTAMP,
                debt_to_equity REAL,
                period TEXT DEFAULT 'annual',
                FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                UNIQUE(symbol, year, period)
            )
        """)

        # Restore data
        print("Restoring data...")
        for row in backup_data:
            # Map old data to new schema
            # Old schema: id, symbol, year, eps, revenue, fiscal_end, last_updated, debt_to_equity, period
            cursor.execute("""
                INSERT OR REPLACE INTO earnings_history
                (id, symbol, year, earnings_per_share, revenue, fiscal_end, last_updated, debt_to_equity, period)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, row)

        conn.commit()
        print(f"✓ Successfully migrated {len(backup_data)} records")
        print("✓ earnings_history table now supports quarterly and annual data for the same year")

        return True

    except Exception as e:
        print(f"ERROR during migration: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'stocks.db'

    print("=" * 60)
    print("EARNINGS HISTORY TABLE MIGRATION")
    print("=" * 60)
    print()
    print("This will modify the earnings_history table to support")
    print("storing both quarterly and annual data for the same year.")
    print()
    print(f"Database: {db_path}")
    print()

    response = input("Proceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        sys.exit(0)

    success = migrate_earnings_history(db_path)

    if success:
        print()
        print("=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Restart your backend server")
        print("2. Re-screen stocks to populate both quarterly and annual data")
        print("3. Toggle between Annual/Quarterly views in the UI")
        sys.exit(0)
    else:
        print()
        print("Migration failed. Please check the error messages above.")
        sys.exit(1)
