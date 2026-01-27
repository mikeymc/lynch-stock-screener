#!/usr/bin/env python3
"""Quick test to verify expertise level functionality."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from database import Database

def test_expertise_level():
    """Test the expertise level getter and setter."""
    print("Testing expertise level functionality...")

    # Connect to database
    db = Database()

    # Test getting default expertise level for a test user
    # Note: This assumes user with ID 1 exists
    try:
        level = db.get_user_expertise_level(1)
        print(f"✓ Successfully retrieved expertise level: {level}")
    except Exception as e:
        print(f"✗ Error getting expertise level: {e}")
        return False

    # Test setting expertise level
    try:
        db.set_user_expertise_level(1, 'expert')
        db.flush()
        print("✓ Successfully set expertise level to 'expert'")
    except Exception as e:
        print(f"✗ Error setting expertise level: {e}")
        return False

    # Verify it was set
    try:
        new_level = db.get_user_expertise_level(1)
        if new_level == 'expert':
            print(f"✓ Verified expertise level changed to: {new_level}")
        else:
            print(f"✗ Expertise level mismatch. Expected 'expert', got '{new_level}'")
            return False
    except Exception as e:
        print(f"✗ Error verifying expertise level: {e}")
        return False

    # Reset back to practicing
    try:
        db.set_user_expertise_level(1, 'practicing')
        db.flush()
        print("✓ Reset expertise level to 'practicing'")
    except Exception as e:
        print(f"✗ Error resetting expertise level: {e}")
        return False

    print("\n✅ All tests passed!")
    return True

if __name__ == '__main__':
    success = test_expertise_level()
    sys.exit(0 if success else 1)
