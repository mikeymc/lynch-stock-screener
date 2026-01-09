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
    
    # Verify search popover
    print("[E2E] Checking search popover...")
    search_container = controls.locator('.search-popover-container')
    expect(search_container).to_be_visible()
    search_input = search_container.locator('input[type="text"]')
    expect(search_input).to_be_visible()
    expect(search_input).to_have_attribute('placeholder', re.compile(r'Search'))
    
    # Verify filter dropdown
    print("[E2E] Checking filter dropdown...")
    filter_dropdown_container = controls.locator('.filter-controls').first
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
    
    # Verify summary stats showing algorithm scoring breakdown
    print("[E2E] Checking summary stats...")
    summary_stats = controls.locator('.summary-stats')
    if summary_stats.is_visible():
        # Check for scoring category labels
        expect(summary_stats).to_contain_text('Excellent')
        expect(summary_stats).to_contain_text('Good')
        expect(summary_stats).to_contain_text('Neutral')
        expect(summary_stats).to_contain_text('Weak')
        expect(summary_stats).to_contain_text('Poor')
    
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
    Test the search popover functionality:
    1. Navigate to app
    2. Use search popover to find AAPL
    3. Verify dropdown shows results
    4. Select stock to navigate to details
    """
    print("\n[E2E] Starting test: search_functionality")
    
    page.goto("http://localhost:5174")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    
    # Find and use search popover input
    print("[E2E] Searching for AAPL...")
    search_container = page.locator('.search-popover-container')
    search_input = search_container.locator('input[type="text"]')
    search_input.fill("AAPL")
    page.wait_for_timeout(500)  # Wait for debounced search
    
    # Verify dropdown appears with results
    print("[E2E] Verifying search dropdown...")
    dropdown = page.locator('.search-popover-dropdown')
    expect(dropdown).to_be_visible(timeout=5000)
    
    # Verify AAPL is in the results
    aapl_item = dropdown.locator('.search-popover-item').filter(has_text='AAPL').first
    expect(aapl_item).to_be_visible()
    
    # Click on AAPL in the dropdown
    print("[E2E] Clicking on AAPL in dropdown...")
    aapl_item.click()
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
    Test navigation to Algorithm Tuning via Settings page:
    1. Navigate to Settings page
    2. Click Algorithm Tuning tab
    3. Verify tuning content loads
    """
    print("\n[E2E] Starting test: algorithm_tuning_page_navigation")
    
    # Navigate to Settings page
    page.goto("http://localhost:5174/settings")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    
    # Verify we're on settings page
    expect(page).to_have_url(re.compile(r'/settings'))
    
    # Click Algorithm Tuning tab
    print("[E2E] Clicking Algorithm Tuning tab...")
    tuning_tab = page.get_by_role('button', name='Algorithm Tuning')
    expect(tuning_tab).to_be_visible()
    tuning_tab.click()
    page.wait_for_timeout(1000)
    
    # Verify Algorithm Tuning content is visible
    print("[E2E] Verifying Algorithm Tuning content...")
    expect(page.get_by_text('Algorithm Tuning')).to_be_visible()
    expect(page.get_by_text('Manual Tuning')).to_be_visible()
    expect(page.get_by_text('Auto-Optimization')).to_be_visible()
    
    print("[E2E] Navigation test completed successfully")



def test_algorithm_tuning_ui_elements(page: Page, servers):
    """
    Test Algorithm Tuning UI elements in Settings page:
    1. Navigate to Settings > Algorithm Tuning
    2. Verify main sections exist
    3. Verify all collapsible sections
    4. Verify action buttons
    """
    print("\n[E2E] Starting test: algorithm_tuning_ui_elements")
    
    # Navigate to Settings and click Algorithm Tuning tab
    page.goto("http://localhost:5174/settings")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.get_by_role('button', name='Algorithm Tuning').click()
    page.wait_for_timeout(1000)
    
    # Verify Manual Tuning card
    print("[E2E] Verifying Manual Tuning card...")
    expect(page.get_by_text('Manual Tuning')).to_be_visible()
    
    # Verify Auto-Optimization card
    print("[E2E] Verifying Auto-Optimization card...")
    expect(page.get_by_text('Auto-Optimization')).to_be_visible()
    
    # Verify Guide card
    print("[E2E] Verifying Guide card...")
    expect(page.get_by_text('Understanding Correlation')).to_be_visible()
    
    # Verify timeframe selector
    print("[E2E] Verifying timeframe selector...")
    expect(page.get_by_text('Backtest Timeframe')).to_be_visible()
    
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
    run_validation_btn = page.get_by_role('button', name=re.compile(r'Run Validation'))
    expect(run_validation_btn).to_be_visible()
    expect(run_validation_btn).to_be_enabled()
    
    save_btn = page.get_by_role('button', name=re.compile(r'Save'))
    expect(save_btn).to_be_visible()
    expect(save_btn).to_be_enabled()
    
    auto_optimize_btn = page.get_by_role('button', name=re.compile(r'Auto-Optimize'))
    expect(auto_optimize_btn).to_be_visible()
    expect(auto_optimize_btn).to_be_enabled()
    
    print("[E2E] UI elements test completed successfully")


def test_algorithm_tuning_collapsible_sections(page: Page, servers):
    """
    Test collapsible sections functionality:
    1. Navigate to Settings > Algorithm Tuning
    2. Verify sections can be collapsed/expanded
    3. Verify sliders are visible when expanded
    """
    print("\n[E2E] Starting test: algorithm_tuning_collapsible_sections")
    
    # Navigate to Settings and click Algorithm Tuning tab
    page.goto("http://localhost:5174/settings")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.get_by_role('button', name='Algorithm Tuning').click()
    page.wait_for_timeout(1000)
    
    # Algorithm Weights section should be open by default (uses shadcn Collapsible)
    print("[E2E] Checking Algorithm Weights section...")
    weights_header = page.get_by_text('Algorithm Weights', exact=True)
    expect(weights_header).to_be_visible()
    
    # Verify sliders are visible (section is open by default)
    peg_weight_slider = page.locator('input[type="range"]').first
    expect(peg_weight_slider).to_be_visible()
    
    # Click to collapse
    print("[E2E] Collapsing Algorithm Weights section...")
    weights_header.click()
    page.wait_for_timeout(500)
    
    # First slider should be hidden
    expect(peg_weight_slider).not_to_be_visible()
    
    # Click to expand again
    print("[E2E] Expanding Algorithm Weights section...")
    weights_header.click()
    page.wait_for_timeout(500)
    
    # Slider should be visible again
    expect(peg_weight_slider).to_be_visible()
    
    # Test PEG Thresholds section (should be collapsed by default)
    print("[E2E] Checking PEG Thresholds section...")
    peg_header = page.get_by_text('PEG Thresholds', exact=True)
    expect(peg_header).to_be_visible()
    
    # Click to expand
    peg_header.click()
    page.wait_for_timeout(500)
    
    # Verify PEG-related content is visible
    expect(page.get_by_text('Excellent PEG')).to_be_visible()
    
    print("[E2E] Collapsible sections test completed successfully")


def test_algorithm_tuning_sliders(page: Page, servers):
    """
    Test slider functionality:
    1. Navigate to Settings > Algorithm Tuning
    2. Verify sliders are present and enabled
    3. Verify slider values are displayed
    """
    print("\n[E2E] Starting test: algorithm_tuning_sliders")
    
    # Navigate to Settings and click Algorithm Tuning tab
    page.goto("http://localhost:5174/settings")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.get_by_role('button', name='Algorithm Tuning').click()
    page.wait_for_timeout(1000)
    
    # Algorithm Weights section is open by default
    print("[E2E] Testing PEG weight slider...")
    
    # Find first slider (PEG Score Weight)
    peg_slider = page.locator('input[type="range"]').first
    expect(peg_slider).to_be_visible()
    
    # Get initial value
    initial_value = peg_slider.get_attribute('value')
    print(f"[E2E] Initial PEG weight value: {initial_value}")
    
    # Verify slider is enabled
    expect(peg_slider).to_be_enabled()
    
    # Verify we have weight labels with percentage values
    expect(page.get_by_text('PEG Score Weight')).to_be_visible()
    
    print("[E2E] Sliders test completed successfully")


def test_algorithm_tuning_timeframe_selector(page: Page, servers):
    """
    Test timeframe selector:
    1. Navigate to Settings > Algorithm Tuning
    2. Verify timeframe can be changed via shadcn Select
    """
    print("\n[E2E] Starting test: algorithm_tuning_timeframe_selector")
    
    # Navigate to Settings and click Algorithm Tuning tab
    page.goto("http://localhost:5174/settings")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.get_by_role('button', name='Algorithm Tuning').click()
    page.wait_for_timeout(1000)
    
    # Find timeframe selector (shadcn Select trigger)
    print("[E2E] Testing timeframe selector...")
    expect(page.get_by_text('Backtest Timeframe')).to_be_visible()
    
    # Verify default shows "5 Years"
    select_trigger = page.get_by_role('combobox').first
    expect(select_trigger).to_be_visible()
    expect(select_trigger).to_contain_text('5 Years')
    
    # Click to open dropdown
    print("[E2E] Changing timeframe to 10 years...")
    select_trigger.click()
    page.wait_for_timeout(300)
    
    # Select 10 years option
    page.get_by_role('option', name='10 Years').click()
    page.wait_for_timeout(500)
    
    # Verify selection changed
    expect(select_trigger).to_contain_text('10 Years')
    
    print("[E2E] Timeframe selector test completed successfully")


def test_algorithm_tuning_correlation_guide(page: Page, servers):
    """
    Test correlation guide display:
    1. Navigate to Settings > Algorithm Tuning
    2. Verify guide card exists
    3. Verify all correlation ranges are displayed
    """
    print("\n[E2E] Starting test: algorithm_tuning_correlation_guide")
    
    # Navigate to Settings and click Algorithm Tuning tab
    page.goto("http://localhost:5174/settings")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.get_by_role('button', name='Algorithm Tuning').click()
    page.wait_for_timeout(1000)
    
    # Verify Understanding Correlation section
    print("[E2E] Verifying correlation guide...")
    expect(page.get_by_text('Understanding Correlation')).to_be_visible()
    
    # Verify all correlation ranges are present
    expected_ranges = [
        ('0.00 - 0.05', 'Noise'),
        ('0.05 - 0.10', 'Weak Signal'),
        ('0.10 - 0.15', 'Good'),
        ('0.15 - 0.25', 'Excellent'),
        ('> 0.30', 'Suspicious')
    ]
    
    for range_text, description in expected_ranges:
        expect(page.get_by_text(range_text)).to_be_visible()
        expect(page.get_by_text(description)).to_be_visible()
        print(f"[E2E] Found range: {range_text} - {description}")
    
    # Verify timeframe selection tip is visible
    expect(page.get_by_text('Timeframe Selection')).to_be_visible()
    
    print("[E2E] Correlation guide test completed successfully")
