import requests
import json
import time

BASE_URL = "http://localhost:8080/api"

def test_caching():
    symbol = "AMZN"
    section = "growth"
    
    print(f"1. Generating analysis for {symbol} ({section}) - Force Refresh...")
    start = time.time()
    resp = requests.post(f"{BASE_URL}/stock/{symbol}/chart-analysis", json={
        "section": section,
        "force_refresh": True
    })
    print(f"   Status: {resp.status_code}")
    data = resp.json()
    print(f"   Cached: {data.get('cached')}")
    print(f"   Time: {time.time() - start:.2f}s")
    
    if resp.status_code != 200:
        print("   Error:", data)
        return

    print("\n2. Fetching analysis again - Should be Cached...")
    start = time.time()
    resp = requests.post(f"{BASE_URL}/stock/{symbol}/chart-analysis", json={
        "section": section,
        "force_refresh": False
    })
    print(f"   Status: {resp.status_code}")
    data = resp.json()
    print(f"   Cached: {data.get('cached')}")
    print(f"   Time: {time.time() - start:.2f}s")
    
    if data.get('cached') is True:
        print("\nSUCCESS: Caching is working via API.")
    else:
        print("\nFAILURE: Response was not cached.")

if __name__ == "__main__":
    test_caching()
