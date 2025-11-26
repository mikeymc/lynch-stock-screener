#!/usr/bin/env python3
"""
Initialize SEC Bulk Data Cache

Downloads and extracts the SEC companyfacts.zip file containing
financial data for all publicly traded companies.

Usage:
    python init_sec_cache.py [--force]

Options:
    --force    Force re-download even if cache is valid
"""

import sys
import argparse
from edgar_fetcher import EdgarFetcher

def main():
    parser = argparse.ArgumentParser(description='Initialize SEC bulk data cache')
    parser.add_argument('--force', action='store_true', 
                       help='Force re-download even if cache is valid')
    parser.add_argument('--cache-dir', default='./sec_cache',
                       help='Cache directory (default: ./sec_cache)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("SEC Bulk Data Cache Initialization")
    print("=" * 60)
    print()
    
    # Initialize fetcher with bulk cache enabled
    fetcher = EdgarFetcher(
        user_agent="Lynch Stock Screener mikey@example.com",
        use_bulk_cache=True,
        cache_dir=args.cache_dir
    )
    
    # Initialize cache
    print("Starting cache initialization...")
    print()
    
    try:
        success = fetcher.initialize_sec_cache(force=args.force)
    except Exception as e:
        print(f"Error during initialization: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    if success:
        print()
        print("=" * 60)
        print("✓ Cache initialization successful!")
        print("=" * 60)
        
        # Show cache stats
        if fetcher.bulk_manager:
            stats = fetcher.bulk_manager.get_cache_stats()
            print()
            print("Cache Statistics:")
            print(f"  Status: {stats.get('status')}")
            print(f"  Last Updated: {stats.get('last_updated', 'N/A')}")
            print(f"  Age: {stats.get('age_days', 0)} days, {stats.get('age_hours', 0)} hours")
            print(f"  Total Files: {stats.get('total_files', 0):,}")
            print(f"  Zip Size: {stats.get('zip_size_mb', 0):.1f} MB")
            print(f"  Extract Dir: {stats.get('extract_dir', 'N/A')}")
        
        return 0
    else:
        print()
        print("=" * 60)
        print("✗ Cache initialization failed")
        print("=" * 60)
        print("Check the logs above for error details")
        return 1

if __name__ == '__main__':
    sys.exit(main())
