#!/usr/bin/env python3
# ABOUTME: Migrates SEC bulk cache data from filesystem JSON files to PostgreSQL
# ABOUTME: Reads companyfacts from sec_cache and stores in normalized database schema

import os
import sys
import json
import psycopg2
from psycopg2.extras import execute_batch
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SECPostgresMigrator:
    """Migrates SEC bulk data from filesystem to PostgreSQL"""

    def __init__(self,
                 sec_cache_dir: str = "./sec_cache/companyfacts",
                 db_host: str = "localhost",
                 db_port: int = 5432,
                 db_name: str = "lynch_stocks",
                 db_user: str = "lynch",
                 db_password: str = "lynch_dev_password"):

        self.sec_cache_dir = Path(sec_cache_dir)
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
        self.conn = psycopg2.connect(**self.db_params)
        logger.info("Connected to PostgreSQL")

    def create_schema(self):
        """Create database schema for SEC data"""
        logger.info("Creating database schema...")

        with self.conn.cursor() as cur:
            # Drop existing tables if they exist
            cur.execute("DROP TABLE IF EXISTS company_facts CASCADE")

            # Create company_facts table with JSONB
            cur.execute("""
                CREATE TABLE company_facts (
                    cik TEXT PRIMARY KEY,
                    entity_name TEXT,
                    ticker TEXT,
                    facts JSONB NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            cur.execute("CREATE INDEX idx_company_facts_ticker ON company_facts(ticker)")
            cur.execute("CREATE INDEX idx_company_facts_entity_name ON company_facts(entity_name)")
            cur.execute("CREATE INDEX idx_company_facts_facts_gin ON company_facts USING GIN (facts)")

            self.conn.commit()
            logger.info("Schema created successfully")

    def extract_ticker_from_facts(self, facts: dict) -> str:
        """
        Try to extract ticker from company facts
        The SEC API doesn't include ticker directly in company facts,
        so we'll need to populate this separately from the ticker->CIK mapping
        """
        # For now, return empty string - we'll populate from ticker mapping later
        return ""

    def migrate_all_companies(self, batch_size: int = 100, limit: int = None):
        """
        Migrate all company JSON files to PostgreSQL

        Args:
            batch_size: Number of records to insert per batch
            limit: Optional limit on number of companies to migrate (for testing)
        """
        if not self.sec_cache_dir.exists():
            logger.error(f"SEC cache directory not found: {self.sec_cache_dir}")
            return

        json_files = list(self.sec_cache_dir.glob("CIK*.json"))
        total_files = len(json_files)

        if limit:
            json_files = json_files[:limit]
            logger.info(f"Limiting migration to {limit} companies (out of {total_files} total)")
        else:
            logger.info(f"Found {total_files} company files to migrate")

        batch = []
        processed = 0
        errors = 0

        for i, json_file in enumerate(json_files, 1):
            try:
                # Extract CIK from filename (CIK0000320193.json -> 0000320193)
                cik = json_file.stem.replace('CIK', '')

                # Load company facts
                with open(json_file, 'r') as f:
                    facts = json.load(f)

                entity_name = facts.get('entityName', '')
                ticker = self.extract_ticker_from_facts(facts)

                # Add to batch
                batch.append({
                    'cik': cik,
                    'entity_name': entity_name,
                    'ticker': ticker,
                    'facts': json.dumps(facts),
                    'last_updated': datetime.now()
                })

                # Insert batch when it reaches batch_size
                if len(batch) >= batch_size:
                    self._insert_batch(batch)
                    processed += len(batch)
                    batch = []

                    # Progress update every 10 batches
                    if processed % (batch_size * 10) == 0:
                        progress_pct = (i / len(json_files)) * 100
                        logger.info(f"Progress: {processed}/{len(json_files)} ({progress_pct:.1f}%)")

            except Exception as e:
                logger.error(f"Error processing {json_file.name}: {e}")
                errors += 1
                continue

        # Insert remaining batch
        if batch:
            self._insert_batch(batch)
            processed += len(batch)

        logger.info(f"Migration complete: {processed} companies inserted, {errors} errors")

        # Get database size
        self._print_database_stats()

    def _insert_batch(self, batch: list):
        """Insert a batch of company records"""
        with self.conn.cursor() as cur:
            execute_batch(cur, """
                INSERT INTO company_facts (cik, entity_name, ticker, facts, last_updated)
                VALUES (%(cik)s, %(entity_name)s, %(ticker)s, %(facts)s, %(last_updated)s)
                ON CONFLICT (cik) DO UPDATE SET
                    entity_name = EXCLUDED.entity_name,
                    ticker = EXCLUDED.ticker,
                    facts = EXCLUDED.facts,
                    last_updated = EXCLUDED.last_updated
            """, batch)
            self.conn.commit()

    def populate_tickers_from_mapping(self):
        """
        Populate ticker field using SEC's ticker->CIK mapping
        This runs after initial migration to add ticker symbols
        """
        import requests

        logger.info("Fetching ticker->CIK mapping from SEC...")

        try:
            # Fetch ticker mapping
            url = "https://www.sec.gov/files/company_tickers.json"
            headers = {'User-Agent': 'Stock Screener mikey@example.com'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build CIK->ticker mapping
            cik_to_ticker = {}
            for entry in data.values():
                ticker = entry.get('ticker', '').upper()
                cik = str(entry.get('cik_str', '')).zfill(10)
                cik_to_ticker[cik] = ticker

            logger.info(f"Found {len(cik_to_ticker)} ticker mappings")

            # Update database
            updated = 0
            with self.conn.cursor() as cur:
                for cik, ticker in cik_to_ticker.items():
                    cur.execute("""
                        UPDATE company_facts
                        SET ticker = %s
                        WHERE cik = %s
                    """, (ticker, cik))
                    if cur.rowcount > 0:
                        updated += 1

                self.conn.commit()

            logger.info(f"Updated {updated} companies with ticker symbols")

        except Exception as e:
            logger.error(f"Error populating tickers: {e}")

    def _print_database_stats(self):
        """Print database size and statistics"""
        with self.conn.cursor() as cur:
            # Get total companies
            cur.execute("SELECT COUNT(*) FROM company_facts")
            total_companies = cur.fetchone()[0]

            # Get database size
            cur.execute("""
                SELECT pg_size_pretty(pg_database_size(%s))
            """, (self.db_params['dbname'],))
            db_size = cur.fetchone()[0]

            # Get table size
            cur.execute("""
                SELECT pg_size_pretty(pg_total_relation_size('company_facts'))
            """)
            table_size = cur.fetchone()[0]

            logger.info("=" * 60)
            logger.info("DATABASE STATISTICS")
            logger.info("=" * 60)
            logger.info(f"Total companies:     {total_companies:,}")
            logger.info(f"Database size:       {db_size}")
            logger.info(f"company_facts table: {table_size}")
            logger.info("=" * 60)

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Migrate SEC bulk data to PostgreSQL')
    parser.add_argument('--cache-dir', default='./sec_cache/companyfacts',
                        help='SEC cache directory (default: ./sec_cache/companyfacts)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of companies to migrate (for testing)')
    parser.add_argument('--skip-schema', action='store_true',
                        help='Skip schema creation (use for incremental updates)')
    parser.add_argument('--update-tickers', action='store_true',
                        help='Update ticker symbols from SEC mapping')

    args = parser.parse_args()

    migrator = SECPostgresMigrator(sec_cache_dir=args.cache_dir)

    try:
        migrator.connect()

        if not args.skip_schema:
            migrator.create_schema()

        if args.update_tickers:
            migrator.populate_tickers_from_mapping()
        else:
            migrator.migrate_all_companies(limit=args.limit)

            # Populate tickers after migration
            logger.info("Populating ticker symbols...")
            migrator.populate_tickers_from_mapping()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        migrator.close()


if __name__ == '__main__':
    main()
