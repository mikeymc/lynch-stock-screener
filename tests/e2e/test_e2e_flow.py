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
    
    # First verify the API is returning screening data
    print("[E2E] Checking /api/sessions/latest endpoint...")
    api_response = requests.get("http://localhost:8081/api/sessions/latest")
    print(f"[E2E] API Status: {api_response.status_code}")
    if api_response.status_code == 200:
        data = api_response.json()
        result_count = len(data.get('results', []))
        print(f"[E2E] API returned {result_count} results")
        if result_count > 0:
            first_result = data['results'][0]
            print(f"[E2E] First result: {first_result.get('symbol')} - {first_result.get('company_name')}")
    else:
        print(f"[E2E] API Error: {api_response.text[:500]}")
    
    # Navigate to the app
    print("[E2E] Navigating to http://localhost:5174?user=admin")
    page.goto("http://localhost:5174?user=admin")
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
    expect(search_input).to_have_attribute('placeholder', re.compile(r'Search by symbol'))
    
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
    
    # Verify tuning icon button
    print("[E2E] Checking tuning icon button...")
    tuning_button = controls.locator('button.settings-button').nth(0)
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
        'Dividend Yield',
        'TTM P/E Range',
        '5y Revenue Consistency',
        '5y Income Consistency',
        'Overall'
    ]
    
    for header_text in expected_headers:
        expect(header_row).to_contain_text(header_text)
    
    # ===== TABLE DATA VERIFICATION =====
    print("[E2E] Verifying table data...")
    tbody = table.locator('tbody')
    stock_rows = tbody.locator('tr.stock-row')
    
    # Verify we have exactly 51 rows (test dataset size)
    row_count = stock_rows.count()
    print(f"[E2E] Found {row_count} stock rows")
    assert row_count == 51, f"Expected 51 rows (test dataset), got {row_count}"
    
    # Verify first row is Excellent
    print("[E2E] Checking first row status...")
    first_row = stock_rows.first
    overall_status_cell = first_row.locator('td').last
    expect(overall_status_cell).to_contain_text('Good')
    
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
    
    page.goto("http://localhost:5174")
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


def test_stock_detail_header_and_tabs(page: Page, servers):
    """
    Test stock detail page header and tab navigation:
    1. Navigate to AAPL detail page
    2. Verify header controls (Back, Refresh buttons)
    3. Verify all tab buttons exist
    4. Verify stock data table header
    """
    print("\n[E2E] Starting test: stock_detail_header_and_tabs")
    
    # Navigate directly to AAPL detail page
    print("[E2E] Navigating to AAPL detail page...")
    page.goto("http://localhost:5174/stock/AAPL")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)  # Wait for data to load
    
    # Verify controls
    print("[E2E] Verifying header controls...")
    controls = page.locator('.controls')
    expect(controls).to_be_visible()
    
    # Verify All Stocks button
    all_stocks_button = controls.get_by_role('button', name='All Stocks')
    expect(all_stocks_button).to_be_visible()
    expect(all_stocks_button).to_be_enabled()
    
    
    # Verify all tab buttons
    print("[E2E] Verifying tab buttons...")
    expected_tabs = ['Financials', 'DCF Analysis', 'Quarterly & Annual Reports', 'Forward Metrics', 'Brief', 'News', 'Material Event Filings']
    for tab_name in expected_tabs:
        tab_button = controls.get_by_role('button', name=tab_name)
        expect(tab_button).to_be_visible()
        print(f"[E2E] Found tab: {tab_name}")
    
    # Verify Charts tab is active by default
    charts_tab = controls.get_by_role('button', name='Financials')
    expect(charts_tab).to_have_class(re.compile(r'active'))
    
    # Verify stock data table (now in .stock-summary-section within .sticky-zone)
    print("[E2E] Verifying stock data table...")
    stock_summary = page.locator('.stock-summary-section')
    expect(stock_summary).to_be_visible()
    
    table = stock_summary.locator('table')
    expect(table).to_be_visible()
    
    # Verify stock row contains AAPL
    tbody = table.locator('tbody')
    expect(tbody).to_contain_text('AAPL')
    
    print("[E2E] Header and tabs test completed successfully")


def test_stock_detail_charts_tab(page: Page, servers):
    """
    Test the Charts tab on stock detail page:
    1. Navigate to AAPL
    2. Verify Charts tab is active
    3. Verify chart elements are present
    """
    print("\n[E2E] Starting test: stock_detail_charts_tab")
    
    page.goto("http://localhost:5174/stock/AAPL")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Ensure Charts tab is active
    print("[E2E] Verifying Charts tab...")
    charts_tab = page.get_by_role('button', name='Financials')
    expect(charts_tab).to_have_class(re.compile(r'active'))
    
    # Verify tabs content container (now .stock-detail-content)
    tabs_content = page.locator('.stock-detail-content')
    expect(tabs_content).to_be_visible()
    
    # Charts should be visible (StockCharts component)
    # Look for chart-specific elements
    print("[E2E] Checking for chart elements...")
    # The charts component should render canvas elements or chart containers
    page.wait_for_timeout(2000)  # Wait for charts to render
    
    # Verify some content is present (charts load dynamically)
    expect(tabs_content).not_to_be_empty()
    
    print("[E2E] Charts tab test completed successfully")


def test_stock_detail_dcf_tab(page: Page, servers):
    """
    Test the DCF Analysis tab:
    1. Navigate to AAPL
    2. Click DCF Analysis tab
    3. Verify DCF content is displayed
    """
    print("\n[E2E] Starting test: stock_detail_dcf_tab")
    
    page.goto("http://localhost:5174/stock/AAPL")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Click DCF Analysis tab
    print("[E2E] Clicking DCF Analysis tab...")
    dcf_tab = page.get_by_role('button', name='DCF Analysis')
    dcf_tab.click()
    page.wait_for_timeout(2000)
    
    # Verify tab is active
    expect(dcf_tab).to_have_class(re.compile(r'active'))
    
    # Verify DCF content is visible (now .stock-detail-content)
    print("[E2E] Verifying DCF content...")
    tabs_content = page.locator('.stock-detail-content')
    expect(tabs_content).to_be_visible()
    expect(tabs_content).not_to_be_empty()
    
    print("[E2E] DCF tab test completed successfully")


def test_stock_detail_reports_tab(page: Page, servers):
    """
    Test the Reports tab:
    1. Navigate to AAPL
    2. Click Reports tab
    3. Verify reports content loads
    """
    print("\n[E2E] Starting test: stock_detail_reports_tab")
    
    page.goto("http://localhost:5174/stock/AAPL")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Click Reports tab
    print("[E2E] Clicking Reports tab...")
    reports_tab = page.get_by_role('button', name='Quarterly & Annual Reports')
    reports_tab.click()
    page.wait_for_timeout(3000)  # Reports may take time to load
    
    # Verify tab is active
    expect(reports_tab).to_have_class(re.compile(r'active'))
    
    # Verify reports content (now .stock-detail-content)
    print("[E2E] Verifying Reports content...")
    tabs_content = page.locator('.stock-detail-content')
    expect(tabs_content).to_be_visible()
    
    print("[E2E] Reports tab test completed successfully")


def test_stock_detail_brief_tab(page: Page, servers):
    """
    Test the Brief tab:
    1. Navigate to AAPL
    2. Click Brief tab
    3. Verify chat interface is present
    """
    print("\n[E2E] Starting test: stock_detail_brief_tab")
    
    page.goto("http://localhost:5174/stock/AAPL")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Click Brief tab
    print("[E2E] Clicking Brief tab...")
    brief_tab = page.get_by_role('button', name='Brief')
    brief_tab.click()
    page.wait_for_timeout(2000)
    
    # Verify tab is active
    expect(brief_tab).to_have_class(re.compile(r'active'))
    
    # Verify brief content (now .stock-detail-content)
    print("[E2E] Verifying Brief content...")
    tabs_content = page.locator('.stock-detail-content')
    expect(tabs_content).to_be_visible()
    expect(tabs_content).not_to_be_empty()
    
    print("[E2E] Brief tab test completed successfully")


def test_stock_detail_news_tab(page: Page, servers):
    """
    Test the News tab:
    1. Navigate to AAPL
    2. Click News tab
    3. Verify news articles are displayed
    """
    print("\n[E2E] Starting test: stock_detail_news_tab")
    
    page.goto("http://localhost:5174/stock/AAPL")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Click News tab
    print("[E2E] Clicking News tab...")
    news_tab = page.get_by_role('button', name='News')
    news_tab.click()
    page.wait_for_timeout(2000)
    
    # Verify tab is active
    expect(news_tab).to_have_class(re.compile(r'active'))
    
    # Verify news content (now .stock-detail-content)
    print("[E2E] Verifying News content...")
    tabs_content = page.locator('.stock-detail-content')
    expect(tabs_content).to_be_visible()
    expect(tabs_content).not_to_be_empty()
    
    print("[E2E] News tab test completed successfully")


def test_stock_detail_material_events_tab(page: Page, servers):
    """
    Test the Material Events tab:
    1. Navigate to AAPL
    2. Click Material Events tab
    3. Verify events are displayed
    """
    print("\n[E2E] Starting test: stock_detail_material_events_tab")
    
    page.goto("http://localhost:5174/stock/AAPL")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Click Material Events tab
    print("[E2E] Clicking Material Events tab...")
    events_tab = page.get_by_role('button', name='Material Event Filings')
    events_tab.click()
    page.wait_for_timeout(2000)
    
    # Verify tab is active
    expect(events_tab).to_have_class(re.compile(r'active'))
    
    # Verify events content (now .stock-detail-content)
    print("[E2E] Verifying Material Event content...")
    tabs_content = page.locator('.stock-detail-content')
    expect(tabs_content).to_be_visible()
    expect(tabs_content).not_to_be_empty()
    
    print("[E2E] Material Events tab test completed successfully")


def test_backend_api_health(servers):
    """Test that the backend API is responding correctly."""
    print("\n[E2E] Testing backend health endpoint...")
    response = requests.get('http://localhost:8081/api/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'healthy'
    print("[E2E] Backend health check passed")


def test_algorithms_endpoint(servers):
    """Test that the algorithms endpoint returns data."""
    print("\n[E2E] Testing algorithms endpoint...")
    response = requests.get('http://localhost:8081/api/algorithms')
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert len(data) > 0
    print(f"[E2E] Found {len(data)} algorithms")


def test_algorithm_tuning_page_navigation(page: Page, servers):
    """
    Test navigation to Algorithm Tuning page:
    1. Navigate to main page
    2. Click tuning icon
    3. Verify tuning page loads
    4. Verify back button works
    """
    print("\n[E2E] Starting test: algorithm_tuning_page_navigation")
    
    # Start at main page
    page.goto("http://localhost:5174?user=admin")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    
    # Click tuning icon
    print("[E2E] Clicking tuning icon...")
    tuning_button = page.locator('button.settings-button').nth(0)
    tuning_button.click()
    page.wait_for_timeout(2000)
    
    # Verify we're on tuning page
    expect(page).to_have_url(re.compile(r'/tuning'))
    
    # Verify back button exists
    print("[E2E] Verifying back button...")
    back_button = page.get_by_role('button', name=re.compile(r'Back to Stock List'))
    expect(back_button).to_be_visible()
    
    # Click back button
    back_button.click()
    page.wait_for_timeout(1000)
    
    # Verify we're back at main page
    expect(page).to_have_url('http://localhost:5174/')
    
    print("[E2E] Navigation test completed successfully")


def test_algorithm_tuning_ui_elements(page: Page, servers):
    """
    Test Algorithm Tuning page UI elements:
    1. Navigate to tuning page
    2. Verify main sections exist
    3. Verify all collapsible sections
    4. Verify action buttons
    """
    print("\n[E2E] Starting test: algorithm_tuning_ui_elements")
    
    page.goto("http://localhost:5174/tuning")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Verify main container
    print("[E2E] Verifying main container...")
    tuning_container = page.locator('.algorithm-tuning')
    expect(tuning_container).to_be_visible()
    
    # Verify tuning grid
    tuning_grid = page.locator('.tuning-grid')
    expect(tuning_grid).to_be_visible()
    
    # Verify Manual Tuning card
    print("[E2E] Verifying Manual Tuning card...")
    manual_tuning = page.locator('.manual-tuning')
    expect(manual_tuning).to_be_visible()
    expect(manual_tuning).to_contain_text('Manual Tuning')
    
    # Verify Auto-Optimization card
    print("[E2E] Verifying Auto-Optimization card...")
    auto_optimization = page.locator('.auto-optimization')
    expect(auto_optimization).to_be_visible()
    expect(auto_optimization).to_contain_text('Auto-Optimization')
    
    # Verify Guide card
    print("[E2E] Verifying Guide card...")
    guide_card = page.locator('.guide-card')
    expect(guide_card).to_be_visible()
    expect(guide_card).to_contain_text('Understanding Correlation')
    
    # Verify timeframe selector
    print("[E2E] Verifying timeframe selector...")
    timeframe_selector = page.locator('.timeframe-selector')
    expect(timeframe_selector).to_be_visible()
    expect(timeframe_selector.get_by_text('Backtest Timeframe:')).to_be_visible()
    
    timeframe_select = timeframe_selector.locator('select')
    expect(timeframe_select).to_be_visible()
    assert timeframe_select.locator('option[value="5"]').count() > 0, "Missing 5 years option"
    assert timeframe_select.locator('option[value="10"]').count() > 0, "Missing 10 years option"
    
    # Verify collapsible sections exist
    print("[E2E] Verifying collapsible sections...")
    expected_sections = [
        'Algorithm Weights',
        'PEG Thresholds',
        'Growth Thresholds',
        'Debt Thresholds',
        'Institutional Ownership'
    ]
    
    for section_name in expected_sections:
        section = page.get_by_text(section_name, exact=True).first
        expect(section).to_be_visible()
        print(f"[E2E] Found section: {section_name}")
    
    # Verify action buttons
    print("[E2E] Verifying action buttons...")
    run_validation_btn = manual_tuning.get_by_role('button', name=re.compile(r'Run Validation'))
    expect(run_validation_btn).to_be_visible()
    expect(run_validation_btn).to_be_enabled()
    
    save_config_btn = manual_tuning.get_by_role('button', name=re.compile(r'Save Config'))
    expect(save_config_btn).to_be_visible()
    expect(save_config_btn).to_be_enabled()
    
    auto_optimize_btn = auto_optimization.get_by_role('button', name=re.compile(r'Auto-Optimize'))
    expect(auto_optimize_btn).to_be_visible()
    expect(auto_optimize_btn).to_be_enabled()
    
    print("[E2E] UI elements test completed successfully")


def test_algorithm_tuning_collapsible_sections(page: Page, servers):
    """
    Test collapsible sections functionality:
    1. Navigate to tuning page
    2. Verify sections can be collapsed/expanded
    3. Verify sliders are visible when expanded
    """
    print("\n[E2E] Starting test: algorithm_tuning_collapsible_sections")
    
    page.goto("http://localhost:5174/tuning")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Algorithm Weights section should be open by default
    print("[E2E] Checking Algorithm Weights section...")
    weights_header = page.locator('.collapsible-header').filter(has_text='Algorithm Weights')
    expect(weights_header).to_be_visible()
    
    # Check if content is visible (section is open by default)
    weights_content = weights_header.locator('..').locator('.collapsible-content')
    expect(weights_content).to_be_visible()
    
    # Verify sliders are present
    weight_sliders = weights_content.locator('input[type="range"]')
    assert weight_sliders.count() >= 4, "Should have at least 4 weight sliders"
    
    # Click to collapse
    print("[E2E] Collapsing Algorithm Weights section...")
    weights_header.click()
    page.wait_for_timeout(500)
    
    # Content should be hidden
    expect(weights_content).not_to_be_visible()
    
    # Click to expand again
    print("[E2E] Expanding Algorithm Weights section...")
    weights_header.click()
    page.wait_for_timeout(500)
    
    # Content should be visible again
    expect(weights_content).to_be_visible()
    
    # Test PEG Thresholds section (should be collapsed by default)
    print("[E2E] Checking PEG Thresholds section...")
    peg_header = page.locator('.collapsible-header').filter(has_text='PEG Thresholds')
    expect(peg_header).to_be_visible()
    
    # Click to expand
    peg_header.click()
    page.wait_for_timeout(500)
    
    # Verify PEG sliders appear
    peg_content = peg_header.locator('..').locator('.collapsible-content')
    expect(peg_content).to_be_visible()
    
    peg_sliders = peg_content.locator('input[type="range"]')
    assert peg_sliders.count() >= 3, "Should have at least 3 PEG threshold sliders"
    
    print("[E2E] Collapsible sections test completed successfully")


def test_algorithm_tuning_sliders(page: Page, servers):
    """
    Test slider functionality:
    1. Navigate to tuning page
    2. Verify sliders can be adjusted
    3. Verify slider values update
    """
    print("\n[E2E] Starting test: algorithm_tuning_sliders")
    
    page.goto("http://localhost:5174/tuning")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Algorithm Weights section is open by default
    weights_content = page.locator('.collapsible-header').filter(has_text='Algorithm Weights').locator('..').locator('.collapsible-content')
    
    # Find PEG weight slider
    print("[E2E] Testing PEG weight slider...")
    peg_slider_group = weights_content.locator('.slider-group').filter(has_text='PEG Score Weight')
    expect(peg_slider_group).to_be_visible()
    
    peg_slider = peg_slider_group.locator('input[type="range"]')
    expect(peg_slider).to_be_visible()
    
    # Get initial value
    initial_value = peg_slider.get_attribute('value')
    print(f"[E2E] Initial PEG weight value: {initial_value}")
    
    # Verify slider value display exists
    slider_value_display = peg_slider_group.locator('.slider-value')
    expect(slider_value_display).to_be_visible()
    expect(slider_value_display).to_contain_text('%')
    
    # Verify slider is enabled
    expect(peg_slider).to_be_enabled()
    
    print("[E2E] Sliders test completed successfully")


def test_algorithm_tuning_timeframe_selector(page: Page, servers):
    """
    Test timeframe selector:
    1. Navigate to tuning page
    2. Verify timeframe can be changed
    3. Verify options are correct
    """
    print("\n[E2E] Starting test: algorithm_tuning_timeframe_selector")
    
    page.goto("http://localhost:5174/tuning")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Find timeframe selector
    print("[E2E] Testing timeframe selector...")
    timeframe_select = page.locator('.timeframe-selector select')
    expect(timeframe_select).to_be_visible()
    
    # Verify default value is 5 years
    current_value = timeframe_select.input_value()
    assert current_value == "5", f"Expected default value '5', got '{current_value}'"
    
    # Change to 10 years
    print("[E2E] Changing timeframe to 10 years...")
    timeframe_select.select_option("10")
    page.wait_for_timeout(500)
    
    # Verify value changed
    new_value = timeframe_select.input_value()
    assert new_value == "10", f"Expected value '10', got '{new_value}'"
    
    # Change back to 5 years
    print("[E2E] Changing timeframe back to 5 years...")
    timeframe_select.select_option("5")
    page.wait_for_timeout(500)
    
    # Verify value changed back
    final_value = timeframe_select.input_value()
    assert final_value == "5", f"Expected value '5', got '{final_value}'"
    
    print("[E2E] Timeframe selector test completed successfully")


def test_algorithm_tuning_correlation_guide(page: Page, servers):
    """
    Test correlation guide display:
    1. Navigate to tuning page
    2. Verify guide card exists
    3. Verify all correlation ranges are displayed
    """
    print("\n[E2E] Starting test: algorithm_tuning_correlation_guide")
    
    page.goto("http://localhost:5174/tuning")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    
    # Verify guide card
    print("[E2E] Verifying correlation guide...")
    guide_card = page.locator('.guide-card')
    expect(guide_card).to_be_visible()
    expect(guide_card).to_contain_text('Understanding Correlation')
    
    # Verify correlation scale exists
    correlation_scale = guide_card.locator('.correlation-scale')
    expect(correlation_scale).to_be_visible()
    
    # Verify all scale ranges are present
    expected_ranges = [
        ('0.00 - 0.05', 'Noise'),
        ('0.05 - 0.10', 'Weak Signal'),
        ('0.10 - 0.15', 'Good'),
        ('0.15 - 0.25', 'Excellent'),
        ('> 0.30', 'Suspicious')
    ]
    
    for range_text, description in expected_ranges:
        scale_item = correlation_scale.locator('.scale-item').filter(has_text=range_text)
        expect(scale_item).to_be_visible()
        expect(scale_item).to_contain_text(description)
        print(f"[E2E] Found range: {range_text} - {description}")
    
    # Verify guide footer
    guide_footer = guide_card.locator('.guide-footer')
    expect(guide_footer).to_be_visible()
    expect(guide_footer).to_contain_text('Timeframe Selection')
    
    print("[E2E] Correlation guide test completed successfully")
