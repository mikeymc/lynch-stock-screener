"""
End-to-end browser automation tests using Playwright.

This test suite verifies the critical user path through the application
with the full stack running (Backend + Frontend).
"""

import re
import requests
from playwright.sync_api import Page, expect


def test_app_initialization_and_search(page: Page, servers):
    """
    Test the basic user flow:
    1. Load the application
    2. Verify the page loads correctly
    3. Search for a stock (AAPL)
    4. Verify stock data is displayed
    """
    print("\n[E2E] Starting test: app_initialization_and_search")
    
    # Navigate to the app
    print("[E2E] Navigating to http://localhost:5173")
    page.goto("http://localhost:5173")
    
    # Wait for the page to load
    page.wait_for_load_state("networkidle")
    
    # Verify the page title
    print("[E2E] Verifying page loaded...")
    expect(page).to_have_title(re.compile(r".+"))
    
    # Wait for the main content to be visible
    print("[E2E] Waiting for main content...")
    page.wait_for_selector("body", state="visible")
    page.wait_for_selector("#root", state="visible")
    
    # Wait for React to render
    page.wait_for_timeout(2000)
    
    # Look for stock search input
    print("[E2E] Looking for stock-related elements...")
    search_inputs = page.locator('input[type="text"]')
    
    if search_inputs.count() > 0:
        print(f"[E2E] Found {search_inputs.count()} search input(s), searching for AAPL...")
        search_inputs.first.fill("AAPL")
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)  # Wait for results
    
    # Try to find and click AAPL in the results
    aapl_elements = page.get_by_text("AAPL")
    if aapl_elements.count() > 0:
        print(f"[E2E] Found {aapl_elements.count()} element(s) with 'AAPL', clicking first...")
        aapl_elements.first.click()
        page.wait_for_timeout(3000)  # Wait for stock details to load
        
        # Verify we're on a stock detail page
        expect(page.locator("body")).to_contain_text("AAPL", timeout=5000)
    else:
        print("[E2E] No AAPL elements found on page")
        raise AssertionError("Could not find AAPL in search results")
    
    print("[E2E] Test completed successfully")


def test_backend_api_health(servers):
    """Test that the backend API is responding correctly."""
    print("\n[E2E] Testing backend health endpoint...")
    response = requests.get('http://localhost:8080/api/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'healthy'
    print("[E2E] Backend health check passed")


def test_algorithms_endpoint(servers):
    """Test that the algorithms endpoint returns data."""
    print("\n[E2E] Testing algorithms endpoint...")
    response = requests.get('http://localhost:8080/api/algorithms')
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert len(data) > 0
    print(f"[E2E] Found {len(data)} algorithms")
