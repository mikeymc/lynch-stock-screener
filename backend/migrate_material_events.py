#!/usr/bin/env python3
# ABOUTME: Migration script to add material_events table for SEC 8-K filings
# ABOUTME: Creates new table to store material corporate events separate from news articles

import os
import sys
import psycopg
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MaterialEventsMigration:
    """Adds material_events table for SEC 8-K filings"""

    def __init__(self,
                 db_host: str = "localhost",
                 db_port: int = 5432,
                 db_name: str = "lynch_stocks",
                 db_user: str = "lynch",
                 db_password: str = "lynch_dev_password"):

        self.db_params = {
            'host': db_host,
            'port': db_port,
            'dbname': db_name,
            'user': db_user,
            'password': db_password
        }
        self.conn = None

    def connect(self):
        """Connect to PostgreSQL"""
        logger.info(f"Connecting to PostgreSQL at {self.db_params['host']}:{self.db_params['port']}")
        self.conn = psycopg.connect(**self.db_params)
        logger.info("✓ Connected to PostgreSQL")

    def check_table_exists(self):
        """Check if material_events table already exists"""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'material_events'
                )
            """)
            exists = cur.fetchone()[0]
            return exists

    def create_table(self):
        """Create material_events table"""
        logger.info("Creating material_events table...")

        with self.conn.cursor() as cur:
            # Create material_events table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS material_events (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    description TEXT,
                    source TEXT NOT NULL DEFAULT 'SEC',
                    url TEXT,
                    filing_date DATE,
                    datetime INTEGER,
                    published_date TIMESTAMP,
                    sec_accession_number TEXT,
                    sec_item_codes TEXT[],
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (symbol) REFERENCES stocks(symbol),
                    UNIQUE(symbol, sec_accession_number)
                )
            """)
            logger.info("✓ Created material_events table")

            # Create indexes
            logger.info("Creating indexes...")

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_material_events_symbol_date
                    ON material_events(symbol, datetime DESC)
            """)
            logger.info("✓ Created index: idx_material_events_symbol_date")

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_material_events_type
                    ON material_events(event_type)
            """)
            logger.info("✓ Created index: idx_material_events_type")

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_material_events_accession
                    ON material_events(sec_accession_number)
            """)
            logger.info("✓ Created index: idx_material_events_accession")

            self.conn.commit()
            logger.info("✓ All changes committed")

    def verify_schema(self):
        """Verify the table was created correctly"""
        logger.info("Verifying schema...")

        with self.conn.cursor() as cur:
            # Check table exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'material_events'
                )
            """)
            exists = cur.fetchone()[0]
            if not exists:
                raise Exception("Table material_events was not created!")

            # Check columns
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'material_events'
                ORDER BY ordinal_position
            """)
            columns = cur.fetchall()
            logger.info(f"✓ Table has {len(columns)} columns:")
            for col_name, col_type in columns:
                logger.info(f"  - {col_name}: {col_type}")

            # Check indexes
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'material_events'
            """)
            indexes = cur.fetchall()
            logger.info(f"✓ Table has {len(indexes)} indexes:")
            for idx in indexes:
                logger.info(f"  - {idx[0]}")

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def run_migration(self):
        """Execute full migration"""
        try:
            self.connect()

            # Check if already migrated
            if self.check_table_exists():
                logger.warning("⚠ Table material_events already exists!")
                logger.info("If you need to re-run the migration, manually drop the table first:")
                logger.info("  DROP TABLE material_events CASCADE;")
                return False

            # Create table and indexes
            self.create_table()

            # Verify everything worked
            self.verify_schema()

            logger.info("")
            logger.info("=" * 60)
            logger.info("MIGRATION SUCCESSFUL")
            logger.info("=" * 60)
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Restart your backend server")
            logger.info("2. Test material events API endpoints")
            logger.info("3. Fetch 8-K data for test stocks")

            return True

        except Exception as e:
            logger.error(f"✗ Migration failed: {e}")
            if self.conn:
                self.conn.rollback()
            import traceback
            traceback.print_exc()
            return False

        finally:
            self.close()


if __name__ == '__main__':
    print()
    print("=" * 60)
    print("MATERIAL EVENTS TABLE MIGRATION")
    print("=" * 60)
    print()
    print("This will create a new table 'material_events' for storing")
    print("SEC 8-K filings and other material corporate events.")
    print()
    print("Database: lynch_stocks @ localhost:5432")
    print()

    response = input("Proceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        sys.exit(0)

    print()
    migrator = MaterialEventsMigration()
    success = migrator.run_migration()

    sys.exit(0 if success else 1)
