#!/usr/bin/env python3
# ABOUTME: Utility to refresh test database template with latest production data
# ABOUTME: Re-runs create_test_template.py to rebuild template from current production data

import subprocess
import sys
from pathlib import Path


def main():
    """Refresh test database template by re-running creation script."""
    script_path = Path(__file__).parent / 'create_test_template.py'

    print("Refreshing test database template...")
    print(f"Running: {script_path}")
    print()

    result = subprocess.run([sys.executable, str(script_path)])

    if result.returncode == 0:
        print()
        print("✓ Test template refreshed successfully")
        print("  E2E tests will now use updated data")
    else:
        print()
        print("✗ Test template refresh failed")
        sys.exit(1)


if __name__ == '__main__':
    main()
