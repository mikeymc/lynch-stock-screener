import requests
import json

BASE_URL = "http://localhost:8080/api"

def test_caching():
    symbol = "AMZN"
    section = "growth"
    
    print(f"Testing chart analysis caching for {symbol} ({section})...")
    print("\n1. Force refresh request...")
    resp = requests.post(f"{BASE_URL}/stock/{symbol}/chart-analysis", json={
        "section": section,
        "force_refresh": True
    })
    
    print(f"Status: {resp.status_code}")
    print(f"Response keys: {list(resp.json().keys())}")
    print(f"Full response: {json.dumps(resp.json(), indent=2)[:500]}...")
    
    print("\n2. Normal request (should be cached)...")
    resp2 = requests.post(f"{BASE_URL}/stock/{symbol}/chart-analysis", json={
        "section": section,
        "force_refresh": False
    })
    
    print(f"Status: {resp2.status_code}")
    print(f"Response keys: {list(resp2.json().keys())}")
    data = resp2.json()
    print(f"Cached field: {data.get('cached')}")

if __name__ == "__main__":
    test_caching()
