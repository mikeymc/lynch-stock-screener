#!/usr/bin/env python3
"""Test script for material events database methods"""

from database import Database
from datetime import datetime

def test_material_events():
    """Test saving and retrieving material events"""
    print("=" * 60)
    print("Testing Material Events Database Methods")
    print("=" * 60)
    print()

    # Initialize database
    print("1. Initializing database connection...")
    db = Database()
    print("✓ Connected to database")
    print()

    # Test data - simulate an 8-K filing
    test_symbol = "AAPL"
    test_event = {
        'event_type': '8k',
        'headline': 'SEC 8-K Filing - Test Event',
        'description': 'Test material event for Apple Inc.',
        'source': 'SEC',
        'url': 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000320193',
        'filing_date': datetime(2024, 11, 15).date(),
        'datetime': int(datetime(2024, 11, 15).timestamp()),
        'published_date': datetime(2024, 11, 15).isoformat(),
        'sec_accession_number': '0000320193-24-000001',
        'sec_item_codes': ['5.02', '8.01']
    }

    # Test 1: Save material event
    print("2. Testing save_material_event()...")
    db.save_material_event(test_symbol, test_event)
    db.flush()  # Ensure write queue is processed
    # Wait for batch commit (writer commits every 2 seconds)
    import time
    time.sleep(2.5)
    print("✓ Event saved successfully")
    print()

    # Test 2: Retrieve material events
    print("3. Testing get_material_events()...")
    events = db.get_material_events(test_symbol)
    print(f"✓ Retrieved {len(events)} event(s)")

    assert len(events) > 0, "No events retrieved after saving!"

    if events:
        event = events[0]
        print()
        print("Event details:")
        print(f"  ID: {event['id']}")
        print(f"  Symbol: {event['symbol']}")
        print(f"  Type: {event['event_type']}")
        print(f"  Headline: {event['headline']}")
        print(f"  Source: {event['source']}")
        print(f"  Filing Date: {event['filing_date']}")
        print(f"  SEC Accession: {event['sec_accession_number']}")
        print(f"  Item Codes: {event['sec_item_codes']}")
        print(f"  URL: {event['url']}")

        # Verify data matches
        assert event['symbol'] == test_symbol, "Symbol mismatch!"
        assert event['event_type'] == '8k', "Event type mismatch!"
        assert event['sec_accession_number'] == test_event['sec_accession_number'], "Accession number mismatch!"
        assert event['sec_item_codes'] == test_event['sec_item_codes'], "Item codes mismatch!"
        print()
        print("✓ All fields match expected values")

    print()

    # Test 3: Get cache status
    print("4. Testing get_material_events_cache_status()...")
    cache_status = db.get_material_events_cache_status(test_symbol)

    if cache_status:
        print(f"✓ Cache status retrieved:")
        print(f"  Event count: {cache_status['event_count']}")
        print(f"  Last updated: {cache_status['last_updated']}")
    else:
        print("✗ No cache status found")

    print()

    # Test 4: Test with limit
    print("5. Testing get_material_events() with limit=1...")
    limited_events = db.get_material_events(test_symbol, limit=1)
    print(f"✓ Retrieved {len(limited_events)} event(s) with limit")
    assert len(limited_events) <= 1, "Limit not respected!"
    print()

    # Test 5: Test upsert (conflict resolution)
    print("6. Testing conflict resolution (upsert)...")
    updated_event = test_event.copy()
    updated_event['headline'] = 'SEC 8-K Filing - Updated Test Event'
    db.save_material_event(test_symbol, updated_event)
    db.flush()
    time.sleep(2.5)  # Wait for batch commit

    events_after_update = db.get_material_events(test_symbol)
    if events_after_update:
        print(f"✓ Headline updated: {events_after_update[0]['headline']}")
        assert events_after_update[0]['headline'] == 'SEC 8-K Filing - Updated Test Event', "Update failed!"

    print()

    # Test 6: Test with non-existent symbol
    print("7. Testing with non-existent symbol...")
    no_events = db.get_material_events("NONEXISTENT")
    print(f"✓ Retrieved {len(no_events)} events for non-existent symbol")
    assert len(no_events) == 0, "Should return empty list!"

    no_cache = db.get_material_events_cache_status("NONEXISTENT")
    print(f"✓ Cache status: {no_cache}")
    assert no_cache is None, "Should return None!"

    print()
    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
    print()
    print("Material events database methods are working correctly.")
    print()


if __name__ == '__main__':
    try:
        test_material_events()
    except AssertionError as e:
        print()
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    except Exception as e:
        print()
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
