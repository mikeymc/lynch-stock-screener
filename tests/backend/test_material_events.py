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

    # Test data - simulate an 8-K filing with content_text
    test_symbol = "AAPL"
    test_content = """Item 5.02 Departure of Directors or Certain Officers; Election of Directors

On November 15, 2024, the Board of Directors of Apple Inc. appointed Jane Smith as Chief Financial Officer, effective December 1, 2024. Ms. Smith will succeed John Doe, who announced his retirement.

Ms. Smith, age 45, has served as Senior Vice President of Finance at XYZ Corporation since 2020. Prior to that, she held various leadership positions at ABC Company from 2015 to 2020.

This filing contains forward-looking statements that involve risks and uncertainties. Actual results may differ materially from those projected.

[Content truncated for length]"""

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
        'sec_item_codes': ['5.02', '8.01'],
        'content_text': test_content
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

    # Find our specific test event by accession number
    event = None
    for e in events:
        if e['sec_accession_number'] == test_event['sec_accession_number']:
            event = e
            break

    assert event is not None, f"Test event with accession {test_event['sec_accession_number']} not found!"

    if event:
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
        if event.get('content_text'):
            print(f"  Content Length: {len(event['content_text'])} chars")
            print(f"  Content Preview: {event['content_text'][:100]}...")
        else:
            print("  Content: None")

        # Verify data matches
        assert event['symbol'] == test_symbol, "Symbol mismatch!"
        assert event['event_type'] == '8k', "Event type mismatch!"
        assert event['sec_accession_number'] == test_event['sec_accession_number'], "Accession number mismatch!"
        assert event['sec_item_codes'] == test_event['sec_item_codes'], "Item codes mismatch!"
        assert 'content_text' in event, "content_text field missing!"
        assert event['content_text'] == test_content, "Content text mismatch!"
        print()
        print("✓ All fields match expected values (including content_text)")

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
    updated_event['content_text'] = 'Updated content text with new information'
    db.save_material_event(test_symbol, updated_event)
    db.flush()
    time.sleep(2.5)  # Wait for batch commit

    events_after_update = db.get_material_events(test_symbol)
    updated_event_retrieved = None
    for e in events_after_update:
        if e['sec_accession_number'] == test_event['sec_accession_number']:
            updated_event_retrieved = e
            break

    if updated_event_retrieved:
        print(f"✓ Headline updated: {updated_event_retrieved['headline']}")
        print(f"✓ Content updated: {updated_event_retrieved['content_text'][:50]}...")
        assert updated_event_retrieved['headline'] == 'SEC 8-K Filing - Updated Test Event', "Headline update failed!"
        assert updated_event_retrieved['content_text'] == 'Updated content text with new information', "Content update failed!"

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
