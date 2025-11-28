#!/usr/bin/env python3
# ABOUTME: Updates SEC company facts data in PostgreSQL by streaming from SEC.gov
# ABOUTME: Downloads companyfacts.zip and inserts directly without extracting to disk

import sys
import argparse
import os
from migrate_sec_to_postgres import SECPostgresMigrator

def main():
    parser = argparse.ArgumentParser(
        description='Update SEC company facts data in PostgreSQL',
        epilog='''
Examples:
  # Update all SEC data (downloads ~1GB zip, streams to PostgreSQL):
  python update_sec_data.py

  # Test with only 100 companies:
  python update_sec_data.py --limit 100

  # Use existing zip file instead of downloading:
  python update_sec_data.py --zip-path ./companyfacts.zip

  # Update only ticker symbols (fast):
  python update_sec_data.py --update-tickers-only
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit number of companies to migrate (for testing)')
    parser.add_argument('--zip-path', default=None,
                       help='Path to existing companyfacts.zip (downloads from SEC if not specified)')
    parser.add_argument('--update-tickers-only', action='store_true',
                       help='Only update ticker symbols (fast, no company facts update)')
    parser.add_argument('--skip-schema', action='store_true',
                       help='Skip schema creation (use for updates to existing database)')

    # Get DB credentials from environment
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_port = int(os.environ.get('DB_PORT', '5432'))
    db_name = os.environ.get('DB_NAME', 'lynch_stocks')
    db_user = os.environ.get('DB_USER', 'lynch')
    db_password = os.environ.get('DB_PASSWORD', 'lynch_dev_password')

    args = parser.parse_args()

    print("=" * 70)
    print("SEC Company Facts Update")
    print("=" * 70)
    print()
    print(f"Database: {db_user}@{db_host}:{db_port}/{db_name}")
    print()

    if args.update_tickers_only:
        print("Mode: Update ticker symbols only")
    elif args.zip_path:
        print(f"Mode: Stream from existing zip file: {args.zip_path}")
    else:
        print("Mode: Download and stream from SEC.gov")
        print("Note: This downloads ~1GB and requires ~2GB temp disk space")

    if args.limit:
        print(f"Limit: Processing only {args.limit} companies")

    print()
    print("-" * 70)
    print()

    # Create migrator
    migrator = SECPostgresMigrator(
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password
    )

    try:
        migrator.connect()

        if not args.skip_schema and not args.update_tickers_only:
            response = input("⚠️  This will DROP and recreate the company_facts table. Continue? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                return 0
            migrator.create_schema()

        if args.update_tickers_only:
            migrator.populate_tickers_from_mapping()
        else:
            # Stream from zip to PostgreSQL
            migrator.migrate_from_zip_stream(zip_path=args.zip_path, limit=args.limit)

            # Populate tickers after migration
            print()
            migrator.populate_tickers_from_mapping()

        print()
        print("=" * 70)
        print("✓ Update complete!")
        print("=" * 70)
        return 0

    except KeyboardInterrupt:
        print()
        print("=" * 70)
        print("✗ Update interrupted by user")
        print("=" * 70)
        return 1
    except Exception as e:
        print()
        print("=" * 70)
        print(f"✗ Update failed: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        migrator.close()

if __name__ == '__main__':
    sys.exit(main())
