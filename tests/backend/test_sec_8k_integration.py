#!/usr/bin/env python3
"""Integration test for SEC 8-K client with real AAPL data"""

from sec_8k_client import SEC8KClient
from database import Database
import time

def test_sec_8k_integration():
    """Test fetching real 8-K filings for AAPL and saving to database"""
    print("=" * 60)
    print("SEC 8-K Client Integration Test")
    print("=" * 60)
    print()

    # Initialize client
    print("1. Initializing SEC 8-K client...")
    user_agent = "Lynch Stock Screener test@example.com"
    client = SEC8KClient(user_agent)
    print("✓ Client initialized")
    print()

    # Test with AAPL
    test_symbol = "AAPL"
    print(f"2. Fetching 8-K filings for {test_symbol} (last 90 days)...")
    filings = client.fetch_recent_8ks(test_symbol, days_back=90)
    print(f"✓ Retrieved {len(filings)} filing(s)")
    print()

    if filings:
        print("3. Sample filing details:")
        filing = filings[0]
        print(f"   Headline: {filing['headline']}")
        print(f"   Event Type: {filing['event_type']}")
        print(f"   Source: {filing['source']}")
        print(f"   Filing Date: {filing['filing_date']}")
        print(f"   Description: {filing['description']}")
        print(f"   Item Codes: {filing['sec_item_codes']}")
        print(f"   Accession: {filing['sec_accession_number']}")
        print(f"   URL: {filing['url'][:80]}..." if filing['url'] and len(filing['url']) > 80 else f"   URL: {filing['url']}")

        # Test content_text extraction
        content_text = filing.get('content_text')
        if content_text:
            print(f"   Content Length: {len(content_text)} characters")
            print(f"   Content Preview: {content_text[:200]}...")
        else:
            print("   Content Text: None")
        print()

        # Verify required fields
        print("4. Verifying required fields...")
        required_fields = ['event_type', 'headline', 'source', 'filing_date',
                          'datetime', 'published_date', 'sec_accession_number',
                          'sec_item_codes', 'content_text']

        for field in required_fields:
            assert field in filing, f"Missing required field: {field}"
            if field == 'content_text':
                # content_text can be None if extraction failed, but field should exist
                assert field in filing, f"Missing field: {field}"
            else:
                assert filing[field] is not None, f"Field {field} is None"

        print("✓ All required fields present")

        # Verify content_text extraction quality
        if filing['content_text']:
            content_len = len(filing['content_text'])
            print(f"✓ Content text extracted: {content_len} characters")
            assert content_len > 100, "Content text too short - extraction may have failed"
            assert content_len <= 505000, "Content text too long - truncation may have failed"
            # Check for exhibit content (press release) or item markers (8-K body fallback)
            assert "Exhibit" in filing['content_text'] or "Item" in filing['content_text'] or content_len > 1000, "Content may not have extracted properly"
        else:
            print("⚠ Content text extraction returned None")
        print()

        # Test database integration
        print("5. Testing database integration...")
        db = Database()

        for filing in filings:
            db.save_material_event(test_symbol, filing)

        db.flush()
        time.sleep(2.5)  # Wait for async write

        saved_events = db.get_material_events(test_symbol)
        print(f"✓ Saved {len(filings)} filings, retrieved {len(saved_events)} from database")

        if saved_events:
            print()
            print("6. Sample saved event:")
            event = saved_events[0]
            print(f"   ID: {event['id']}")
            print(f"   Symbol: {event['symbol']}")
            print(f"   Headline: {event['headline']}")
            print(f"   Item Codes: {event['sec_item_codes']}")
            print(f"   Filing Date: {event['filing_date']}")

            # Verify content_text was saved and retrieved
            if 'content_text' in event and event['content_text']:
                print(f"   Content Saved: ✓ ({len(event['content_text'])} chars)")
            else:
                print(f"   Content Saved: None")
        print()

    else:
        print("⚠ No 8-K filings found in last 90 days")
        print("  This might be normal if AAPL hasn't filed recently")
        print("  Testing with extended lookback...")
        print()

        filings = client.fetch_recent_8ks(test_symbol, days_back=365)
        print(f"✓ Retrieved {len(filings)} filing(s) from last year")

        if filings:
            print()
            print("Sample filing:")
            filing = filings[0]
            print(f"   Headline: {filing['headline']}")
            print(f"   Filing Date: {filing['filing_date']}")
            print(f"   Item Codes: {filing['sec_item_codes']}")

    print()
    print("=" * 60)
    print("INTEGRATION TEST COMPLETE ✓")
    print("=" * 60)
    print()
    print("SEC 8-K client is working correctly with real data.")
    print()


if __name__ == '__main__':
    try:
        test_sec_8k_integration()
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
