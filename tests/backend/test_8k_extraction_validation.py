#!/usr/bin/env python3
"""
Validation test for EX-99.x press release extraction from 8-K filings.

Tests extraction across 30 companies:
- 15 large-cap companies (mega-cap, likely frequent 8-K filers)  
- 15 smaller companies (mid/small-cap, less frequent)

Expected outcomes:
- EX-99.1/EX-99.x exhibit content should be extracted when available
- Falls back to 8-K body text when no exhibit available
- Content should contain press release language, not just boilerplate headers
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

from sec_8k_client import SEC8KClient
import time

# 15 Large-cap companies (high likelihood of 8-K filings with press releases)
LARGE_CAP_COMPANIES = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft  
    "GOOGL",  # Alphabet
    "AMZN",   # Amazon
    "NVDA",   # NVIDIA
    "META",   # Meta
    "TSLA",   # Tesla
    "JPM",    # JPMorgan Chase
    "JNJ",    # Johnson & Johnson
    "V",      # Visa
    "WMT",    # Walmart
    "UNH",    # UnitedHealth
    "XOM",    # Exxon Mobil
    "MA",     # Mastercard
    "PG",     # Procter & Gamble
]

# 15 Smaller companies (mix of mid-cap and small-cap)
SMALLER_COMPANIES = [
    "DUOL",   # Duolingo (~$15B)
    "DOCS",   # Doximity (~$5B)
    "SMAR",   # Smartsheet (~$8B)
    "DDOG",   # Datadog (~$50B, actually larger but good for variety)
    "CRWD",   # CrowdStrike (~$90B)
    "ZS",     # Zscaler (~$30B)
    "BILL",   # Bill.com (~$8B)
    "HUBS",   # HubSpot (~$30B)
    "TWLO",   # Twilio (~$12B)
    "NET",    # Cloudflare (~$30B)
    "OKTA",   # Okta (~$14B)
    "TTD",    # Trade Desk (~$55B)
    "VEEV",   # Veeva Systems (~$30B)
    "ZI",     # ZoomInfo (~$4B)
    "PATH",   # UiPath (~$8B)
]


def check_content_quality(content: str) -> dict:
    """Analyze content to determine if it's from an exhibit or 8-K body"""
    if not content:
        return {"type": "none", "quality": "failed", "reason": "No content extracted"}
    
    content_lower = content.lower()
    
    # Indicators of press release / exhibit content
    press_release_indicators = [
        "press release",
        "for immediate release",
        "investor relations",
        "media contact",
        "forward-looking statements",
        "announced today",
        "reports",
        "quarterly results",
        "earnings",
        "fiscal",
        "revenue",
        "guidance",
    ]
    
    # Indicators of 8-K body (not exhibit)
    body_indicators = [
        "item 2.02",
        "item 5.02",
        "item 7.01",
        "item 8.01",
        "item 9.01",
        "pursuant to",
        "securities exchange act",
        "cover page",
        "signature",
        "hereby certifies",
    ]
    
    pr_score = sum(1 for ind in press_release_indicators if ind in content_lower)
    body_score = sum(1 for ind in body_indicators if ind in content_lower)
    
    # Determine content type
    if pr_score > body_score and pr_score >= 3:
        return {
            "type": "exhibit",
            "quality": "good",
            "reason": f"Press release indicators: {pr_score}, Body indicators: {body_score}",
            "length": len(content)
        }
    elif body_score > 0:
        return {
            "type": "8k_body",
            "quality": "fallback",
            "reason": f"Press release indicators: {pr_score}, Body indicators: {body_score}",
            "length": len(content)
        }
    else:
        return {
            "type": "unknown",
            "quality": "unclear",
            "reason": f"PR indicators: {pr_score}, Body: {body_score}",
            "length": len(content)
        }


def test_company(client: SEC8KClient, symbol: str, category: str) -> dict:
    """Test 8-K extraction for a single company"""
    print(f"  Testing {symbol}...", end=" ", flush=True)
    
    try:
        filings = client.fetch_recent_8ks(symbol, days_back=365)
        
        if not filings:
            print("⚠ No 8-Ks found")
            return {
                "symbol": symbol,
                "category": category,
                "filings_found": 0,
                "status": "no_filings"
            }
        
        # Analyze first filing's content
        first_filing = filings[0]
        content = first_filing.get('content_text')
        quality = check_content_quality(content)
        
        status_emoji = "✓" if quality["quality"] == "good" else "○" if quality["quality"] == "fallback" else "?"
        content_len = quality.get("length", 0)
        
        print(f"{status_emoji} {len(filings)} filings, {quality['type']}, {content_len:,} chars")
        
        return {
            "symbol": symbol,
            "category": category,
            "filings_found": len(filings),
            "content_type": quality["type"],
            "content_quality": quality["quality"],
            "content_length": content_len,
            "quality_reason": quality["reason"],
            "headline": first_filing.get("headline", "")[:60],
            "filing_date": str(first_filing.get("filing_date", "")),
            "status": "success"
        }
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return {
            "symbol": symbol,
            "category": category,
            "status": "error",
            "error": str(e)
        }


def main():
    print("=" * 70)
    print("8-K EX-99.x Press Release Extraction Validation")
    print("=" * 70)
    print()
    print("Testing extraction logic across 30 companies (15 large, 15 smaller)")
    print()
    
    # Initialize client
    user_agent = "Lynch Stock Screener test@example.com"
    client = SEC8KClient(user_agent)
    
    results = []
    
    # Test large-cap companies
    print("=" * 50)
    print("LARGE-CAP COMPANIES")
    print("=" * 50)
    for symbol in LARGE_CAP_COMPANIES:
        result = test_company(client, symbol, "large_cap")
        results.append(result)
        time.sleep(0.2)  # Extra delay between companies
    
    print()
    
    # Test smaller companies
    print("=" * 50)
    print("SMALLER COMPANIES")
    print("=" * 50)
    for symbol in SMALLER_COMPANIES:
        result = test_company(client, symbol, "smaller")
        results.append(result)
        time.sleep(0.2)
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    # Aggregate stats
    successful = [r for r in results if r["status"] == "success"]
    no_filings = [r for r in results if r["status"] == "no_filings"]
    errors = [r for r in results if r["status"] == "error"]
    
    exhibit_extracts = [r for r in successful if r.get("content_type") == "exhibit"]
    body_fallbacks = [r for r in successful if r.get("content_type") == "8k_body"]
    unclear = [r for r in successful if r.get("content_type") == "unknown"]
    
    print(f"Total companies tested: {len(results)}")
    print(f"  - Successful fetches: {len(successful)}")
    print(f"  - No filings found: {len(no_filings)}")
    print(f"  - Errors: {len(errors)}")
    print()
    print("Content extraction results (from successful fetches):")
    print(f"  ✓ Exhibit/Press Release content: {len(exhibit_extracts)} ({len(exhibit_extracts)/max(len(successful),1)*100:.0f}%)")
    print(f"  ○ 8-K body fallback: {len(body_fallbacks)} ({len(body_fallbacks)/max(len(successful),1)*100:.0f}%)")
    print(f"  ? Unclear content type: {len(unclear)} ({len(unclear)/max(len(successful),1)*100:.0f}%)")
    
    if successful:
        avg_length = sum(r.get("content_length", 0) for r in successful) / len(successful)
        print(f"\nAverage content length: {avg_length:,.0f} characters")
    
    print()
    
    # Show sample of exhibit extractions
    if exhibit_extracts:
        print("Sample EXHIBIT extractions:")
        for r in exhibit_extracts[:3]:
            print(f"  {r['symbol']}: {r['headline']}")
            print(f"    Filed: {r['filing_date']}, {r['content_length']:,} chars")
        print()
    
    # Show sample of body fallbacks
    if body_fallbacks:
        print("Sample 8-K BODY fallbacks:")
        for r in body_fallbacks[:3]:
            print(f"  {r['symbol']}: {r['headline']}")
            print(f"    Filed: {r['filing_date']}, {r['content_length']:,} chars")
        print()
    
    # Show errors if any
    if errors:
        print("Errors encountered:")
        for r in errors:
            print(f"  {r['symbol']}: {r.get('error', 'Unknown error')}")
        print()
    
    print("=" * 70)
    print("VALIDATION COMPLETE")
    print("=" * 70)
    
    # Return non-zero if too many failures
    if len(errors) > 5 or len(successful) < 20:
        print("⚠ WARNING: High failure rate detected")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
