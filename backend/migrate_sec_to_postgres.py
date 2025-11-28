#!/usr/bin/env python3
# ABOUTME: Migrates SEC bulk data by streaming from zip file to PostgreSQL
# ABOUTME: Downloads companyfacts.zip and inserts directly without extracting

import os
import sys
import json
import psycopg2
from psycopg2.extras import execute_batch
from pathlib import Path
from datetime import datetime
import logging
import zipfile
import requests
import tempfile
import io

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SECPostgresMigrator:
    """Migrates SEC bulk data by streaming from zip to PostgreSQL"""

    ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"

    def __init__(self,
                 sec_cache_dir: str = "./sec_cache/companyfacts",
                 db_host: str = "localhost",
                 db_port: int = 5432,
                 db_name: str = "lynch_stocks",
                 db_user: str = "lynch",
                 db_password: str = "lynch_dev_password",
                 user_agent: str = "Lynch Stock Screener mikey@example.com"):

        self.sec_cache_dir = Path(sec_cache_dir)
        self.db_params = {
            'host': db_host,
            'port': db_port,
            'dbname': db_name,
            'user': db_user,
            'password': db_password
        }
        self.user_agent = user_agent
        self.headers = {
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate'
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

    def migrate_from_zip_stream(self, zip_path: str = None, batch_size: int = 100, limit: int = None):
        """
        Stream companyfacts.zip and insert directly to PostgreSQL without extracting

        Args:
            zip_path: Optional path to existing zip file. If None, downloads from SEC
            batch_size: Number of records to insert per batch
            limit: Optional limit on number of companies to migrate (for testing)
        """
        if zip_path and not Path(zip_path).exists():
            logger.error(f"Zip file not found: {zip_path}")
            return

        batch = []
        processed = 0
        errors = 0

        # Download or use existing zip
        if zip_path:
            logger.info(f"Using existing zip file: {zip_path}")
            zip_file = zipfile.ZipFile(zip_path, 'r')
        else:
            logger.info(f"Downloading companyfacts.zip from {self.ZIP_URL}")
            logger.info("This may take 5-10 minutes...")

            # Download to temporary file
            response = requests.get(self.ZIP_URL, headers=self.headers, stream=True, timeout=120)
            response.raise_for_status()

            # Create temp file for zip
            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')

            try:
                # Download with progress
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                chunk_size = 8192
                last_progress = 0

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        temp_zip.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            if progress >= last_progress + 10:
                                logger.info(f"Download progress: {progress:.1f}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
                                last_progress = int(progress / 10) * 10

                temp_zip.close()
                logger.info(f"✓ Download complete")

                # Open the downloaded zip
                zip_file = zipfile.ZipFile(temp_zip.name, 'r')

            except Exception as e:
                temp_zip.close()
                os.unlink(temp_zip.name)
                raise

        try:
            # Get list of JSON files in zip
            json_members = [name for name in zip_file.namelist() if name.startswith('CIK') and name.endswith('.json')]
            total_files = len(json_members)

            if limit:
                json_members = json_members[:limit]
                logger.info(f"Limiting migration to {limit} companies (out of {total_files} total)")
            else:
                logger.info(f"Found {total_files} company files in zip")

            logger.info("Starting streaming migration to PostgreSQL...")

            for i, member_name in enumerate(json_members, 1):
                try:
                    # Extract CIK from filename (CIK0000320193.json -> 0000320193)
                    cik = member_name.replace('CIK', '').replace('.json', '')

                    # Read JSON directly from zip (no extraction to disk)
                    with zip_file.open(member_name) as json_file:
                        facts = json.load(json_file)

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
                            progress_pct = (i / len(json_members)) * 100
                            logger.info(f"Progress: {processed}/{len(json_members)} ({progress_pct:.1f}%)")

                except Exception as e:
                    logger.error(f"Error processing {member_name}: {e}")
                    errors += 1
                    continue

            # Insert remaining batch
            if batch:
                self._insert_batch(batch)
                processed += len(batch)

            logger.info(f"Migration complete: {processed} companies inserted, {errors} errors")

            # Get database size
            self._print_database_stats()

        finally:
            zip_file.close()
            # Clean up temp file if we downloaded
            if not zip_path and 'temp_zip' in locals():
                os.unlink(temp_zip.name)
                logger.info("✓ Cleaned up temporary zip file")

    def migrate_all_companies(self, batch_size: int = 100, limit: int = None):
        """
        Migrate all company JSON files from filesystem to PostgreSQL (legacy method)

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
    parser.add_argument('--zip-path', default=None,
                        help='Path to existing companyfacts.zip (if None, downloads from SEC)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of companies to migrate (for testing)')
    parser.add_argument('--skip-schema', action='store_true',
                        help='Skip schema creation (use for incremental updates)')
    parser.add_argument('--update-tickers', action='store_true',
                        help='Update ticker symbols from SEC mapping')
    parser.add_argument('--stream', action='store_true', default=True,
                        help='Stream from zip file (default: True, recommended)')
    parser.add_argument('--legacy', action='store_true',
                        help='Use legacy filesystem method (requires extracted cache)')

    args = parser.parse_args()

    migrator = SECPostgresMigrator(sec_cache_dir=args.cache_dir)

    try:
        migrator.connect()

        if not args.skip_schema:
            migrator.create_schema()

        if args.update_tickers:
            migrator.populate_tickers_from_mapping()
        else:
            # Use streaming method by default (efficient, no disk space needed)
            if args.legacy:
                logger.info("Using legacy filesystem migration method")
                migrator.migrate_all_companies(limit=args.limit)
            else:
                logger.info("Using streaming migration method (efficient)")
                migrator.migrate_from_zip_stream(zip_path=args.zip_path, limit=args.limit)

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
