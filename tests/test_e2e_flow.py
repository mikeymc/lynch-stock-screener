"""
End-to-end browser automation tests using Playwright.

This test suite verifies the critical user path through the application
with the full stack running (Backend + Frontend).
"""

import re
import requests
from playwright.sync_api import Page, expect


def test_app_initialization_and_ui_elements(page: Page, servers):
    """
    Comprehensive test of the main stock list page UI:
    1. Load the application
    2. Verify control bar elements
    3. Verify table structure and data
    4. Verify pagination controls
    """
    print("\n[E2E] Starting test: app_initialization_and_ui_elements")
    
    # Navigate to the app
    print("[E2E] Navigating to http://localhost:5173")
    page.goto("http://localhost:5173")
    page.wait_for_load_state("networkidle")
    
    # Verify page loaded
    print("[E2E] Verifying page loaded...")
    expect(page).to_have_title(re.compile(r".+"))
    page.wait_for_selector("#root", state="visible")
    page.wait_for_timeout(2000)  # Wait for React to render
    
    # ===== CONTROL BAR VERIFICATION =====
    print("[E2E] Verifying control bar...")
    controls = page.locator('.controls')
    expect(controls).to_be_visible()
    
    # Verify "Screen All Stocks" button
    print("[E2E] Checking 'Screen All Stocks' button...")
    screen_button = controls.get_by_role('button', name='Screen All Stocks')
    expect(screen_button).to_be_visible()
    expect(screen_button).to_be_enabled()
    
    # Verify search bar
    print("[E2E] Checking search bar...")
    filter_controls = controls.locator('.filter-controls').first
    expect(filter_controls.get_by_text('Search:')).to_be_visible()
    search_input = filter_controls.locator('input[type="text"]')
    expect(search_input).to_be_visible()
    expect(search_input).to_have_attribute('placeholder', re.compile(r'Filter by symbol'))
    
    # Verify filter dropdown
    print("[E2E] Checking filter dropdown...")
    filter_dropdown_container = controls.locator('.filter-controls').nth(1)
    expect(filter_dropdown_container.get_by_text('Filter:')).to_be_visible()
    filter_select = filter_dropdown_container.locator('select')
    expect(filter_select).to_be_visible()
    
    # Verify filter options exist (options aren't "visible" but we can check they exist)
    assert filter_select.locator('option[value="all"]').count() > 0, "Missing 'All' option"
    assert filter_select.locator('option[value="watchlist"]').count() > 0, "Missing 'Watchlist' option"
    assert filter_select.locator('option[value="STRONG_BUY"]').count() > 0, "Missing 'Strong Buy' option"
    assert filter_select.locator('option[value="BUY"]').count() > 0, "Missing 'Buy' option"
    assert filter_select.locator('option[value="HOLD"]').count() > 0, "Missing 'Hold' option"
    assert filter_select.locator('option[value="CAUTION"]').count() > 0, "Missing 'Caution' option"
    assert filter_select.locator('option[value="AVOID"]').count() > 0, "Missing 'Avoid' option"
    
    # Verify summary stats (if present)
    print("[E2E] Checking summary stats...")
    summary_stats = controls.locator('.summary-stats')
    if summary_stats.is_visible():
        expect(summary_stats).to_contain_text('Analyzed')
        expect(summary_stats).to_contain_text('stocks')
        # Check for weighted algorithm stats
        expect(summary_stats.locator('.summary-stat.strong-buy')).to_be_visible()
        expect(summary_stats.locator('.summary-stat.buy')).to_be_visible()
        expect(summary_stats.locator('.summary-stat.hold')).to_be_visible()
        expect(summary_stats.locator('.summary-stat.caution')).to_be_visible()
        expect(summary_stats.locator('.summary-stat.avoid')).to_be_visible()
    
    # Verify algorithm selector shows "weighted"
    print("[E2E] Checking algorithm selector...")
    algorithm_selector = controls.locator('.algorithm-selector')
    expect(algorithm_selector).to_be_visible()
    expect(algorithm_selector).to_contain_text('weighted', ignore_case=True)
    
    # Verify filter icon button
    print("[E2E] Checking filter icon button...")
    filter_button = controls.locator('button.filter-button')
    expect(filter_button).to_be_visible()
    expect(filter_button).to_have_attribute('title', 'Advanced Filters')
    
    # Verify settings icon button
    print("[E2E] Checking settings icon button...")
    settings_button = controls.locator('button.settings-button').first
    expect(settings_button).to_be_visible()
    expect(settings_button).to_have_attribute('title', 'Settings')
    
    # Verify tuning icon button
    print("[E2E] Checking tuning icon button...")
    tuning_button = controls.locator('button.settings-button').nth(1)
    expect(tuning_button).to_be_visible()
    expect(tuning_button).to_have_attribute('title', 'Tune Algorithm')
    
    # ===== TABLE VERIFICATION =====
    print("[E2E] Verifying table structure...")
    table_container = page.locator('.table-container')
    expect(table_container).to_be_visible()
    
    table = table_container.locator('table')
    expect(table).to_be_visible()
    
    # Verify table header columns
    print("[E2E] Checking table headers...")
    thead = table.locator('thead')
    header_row = thead.locator('tr')
    
    # Check all expected column headers
    expected_headers = [
        '⭐',  # Watchlist
        'Symbol',
        'Company',
        'Country',
        'Market Cap',
        'Sector',
        'Age (Years)',
        'Price',
        'PEG',
        'P/E',
        'D/E',
        'Inst Own',
        '5Y Rev Growth',
        '5Y Inc Growth',
        'Div Yield',
        'PEG Status',
        'Debt Status',
        'Inst Own Status',
        'Overall'
    ]
    
    for header_text in expected_headers:
        expect(header_row).to_contain_text(header_text)
    
    # ===== TABLE DATA VERIFICATION =====
    print("[E2E] Verifying table data...")
    tbody = table.locator('tbody')
    stock_rows = tbody.locator('tr.stock-row')
    
    # Verify we have exactly 100 rows (one page)
    row_count = stock_rows.count()
    print(f"[E2E] Found {row_count} stock rows")
    assert row_count == 100, f"Expected 100 rows, got {row_count}"
    
    # Verify first row is STRONG_BUY
    print("[E2E] Checking first row status...")
    first_row = stock_rows.first
    overall_status_cell = first_row.locator('td').last
    expect(overall_status_cell).to_contain_text('STRONG_BUY')
    
    # Verify first row has all expected data
    print("[E2E] Verifying first row data completeness...")
    first_row_cells = first_row.locator('td')
    
    # Symbol (index 1)
    symbol_cell = first_row_cells.nth(1)
    expect(symbol_cell.locator('strong')).to_be_visible()
    symbol_text = symbol_cell.locator('strong').inner_text()
    assert len(symbol_text) > 0, "Symbol should not be empty"
    
    # Company name (index 2)
    company_cell = first_row_cells.nth(2)
    company_text = company_cell.inner_text()
    assert company_text != 'N/A', "Company name should have a value"
    
    # Country (index 3)
    country_cell = first_row_cells.nth(3)
    country_text = country_cell.inner_text()
    assert country_text != 'N/A', "Country should have a value"
    
    # Market Cap (index 4)
    market_cap_cell = first_row_cells.nth(4)
    market_cap_text = market_cap_cell.inner_text()
    assert 'B' in market_cap_text or market_cap_text == 'N/A', "Market cap should be in billions or N/A"
    
    # Price (index 7)
    price_cell = first_row_cells.nth(7)
    price_text = price_cell.inner_text()
    assert '$' in price_text or price_text == 'N/A', "Price should have $ or be N/A"
    
    # PEG Ratio (index 8)
    peg_cell = first_row_cells.nth(8)
    peg_text = peg_cell.inner_text()
    # PEG should be a number or N/A
    assert peg_text == 'N/A' or peg_text.replace('.', '').replace('-', '').isdigit(), f"PEG should be numeric or N/A, got: {peg_text}"
    
    # ===== PAGINATION VERIFICATION =====
    print("[E2E] Verifying pagination controls...")
    pagination = page.locator('.pagination')
    expect(pagination).to_be_visible()
    
    # Verify Previous button
    prev_button = pagination.get_by_role('button', name='Previous')
    expect(prev_button).to_be_visible()
    expect(prev_button).to_be_disabled()  # Should be disabled on first page
    
    # Verify Next button
    next_button = pagination.get_by_role('button', name='Next')
    expect(next_button).to_be_visible()
    expect(next_button).to_be_enabled()  # Should be enabled if there are more pages
    
    # Verify page info
    page_info = pagination.locator('.page-info')
    expect(page_info).to_be_visible()
    expect(page_info).to_contain_text('Page 1 of')
    
    # Verify pagination info text
    pagination_info = page.locator('.pagination-info')
    expect(pagination_info).to_be_visible()
    expect(pagination_info).to_contain_text('Showing 1-100 of')
    
    print("[E2E] Test completed successfully")


def test_search_functionality(page: Page, servers):
    """
    Test the search functionality:
    1. Navigate to app
    2. Use search to find AAPL
    3. Verify filtered results
    4. Click on stock to view details
    """
    print("\n[E2E] Starting test: search_functionality")
    
    page.goto("http://localhost:5173")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    
    # Find and use search input
    print("[E2E] Searching for AAPL...")
    search_input = page.locator('input[type="text"]').first
    search_input.fill("AAPL")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1000)
    
    # Verify filtered results
    print("[E2E] Verifying search results...")
    table = page.locator('.table-container table')
    tbody = table.locator('tbody')
    stock_rows = tbody.locator('tr.stock-row')
    
    # Should have exactly 1 result
    assert stock_rows.count() == 1, f"Expected 1 AAPL result, got {stock_rows.count()}"
    
    # Verify it's AAPL
    first_row = stock_rows.first
    symbol_cell = first_row.locator('td').nth(1)
    expect(symbol_cell).to_contain_text('AAPL')
    
    # Verify company name contains Apple
    company_cell = first_row.locator('td').nth(2)
    expect(company_cell).to_contain_text('Apple', ignore_case=True)
    
    # Click on the stock
    print("[E2E] Clicking on AAPL...")
    first_row.click()
    page.wait_for_timeout(2000)
    
    # Verify we navigated to stock detail page
    expect(page).to_have_url(re.compile(r'/stock/AAPL'))
    expect(page.locator('body')).to_contain_text('AAPL')
    
    print("[E2E] Search test completed successfully")


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
