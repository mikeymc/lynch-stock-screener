#!/usr/bin/env python3
"""Test expertise guidance loading in stock analyst."""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import Database
from stock_analyst import StockAnalyst

def test_expertise_guidance():
    """Test that expertise guidance is loaded correctly."""
    print("Testing expertise guidance loading...")

    db = Database()
    analyst = StockAnalyst(db)

    # Test loading each expertise level
    for level in ['learning', 'practicing', 'expert']:
        print(f"\n--- Testing level: {level} ---")

        # Set user's expertise level
        db.set_user_expertise_level(1, level)
        db.flush()

        # Load expertise guidance
        guidance = analyst._get_expertise_guidance(user_id=1)

        if guidance:
            print(f"✓ Successfully loaded guidance for '{level}'")
            print(f"  First 100 chars: {guidance[:100]}...")

            # Verify it contains expected content
            if level == 'learning' and 'learning to invest' in guidance.lower():
                print(f"✓ Content matches '{level}' level")
            elif level == 'practicing' and 'working investor' in guidance.lower():
                print(f"✓ Content matches '{level}' level")
            elif level == 'expert' and 'seasoned investor' in guidance.lower():
                print(f"✓ Content matches '{level}' level")
            else:
                print(f"⚠ Content might not match expected level")
        else:
            print(f"✗ Failed to load guidance for '{level}'")
            return False

    print("\n✅ All guidance levels loaded successfully!")
    return True

if __name__ == '__main__':
    success = test_expertise_guidance()
    sys.exit(0 if success else 1)
