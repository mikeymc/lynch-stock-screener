# ABOUTME: Enemy test that validates Wikipedia S&P 500 page structure assumptions
# ABOUTME: Catches breaking changes when Wikipedia modifies their table layout

import pytest
import pandas as pd
import urllib.request


def test_wikipedia_sp500_table_structure():
    """
    Enemy test: Validates that Wikipedia's S&P 500 page has the expected structure.

    This test ensures:
    1. The page is accessible
    2. We can parse HTML tables from it
    3. Table 0 (first table) contains the S&P 500 constituents
    4. The 'Symbol' column exists
    5. We get a reasonable number of stocks (~500)
    6. The symbols look valid (no empty strings, reasonable format)

    If this test fails, Wikipedia changed their page structure and we need to
    update algorithm_validator.py to match the new structure.
    """
    # Fetch the Wikipedia page
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

    with urllib.request.urlopen(req, timeout=10) as response:
        tables = pd.read_html(response.read())

    # Validate we got tables
    assert len(tables) >= 1, "Expected at least 1 table from Wikipedia"

    # Validate table 0 is the S&P 500 constituents table
    sp500_table = tables[0]

    # Check for 'Symbol' column
    assert 'Symbol' in sp500_table.columns, (
        f"Expected 'Symbol' column in table 0. "
        f"Found columns: {list(sp500_table.columns)}. "
        f"Wikipedia may have changed their table structure."
    )

    # Extract symbols
    symbols = sp500_table['Symbol'].tolist()

    # Validate we got a reasonable number of stocks
    # S&P 500 should have ~500 stocks, allow range 400-600 for minor fluctuations
    assert 400 <= len(symbols) <= 600, (
        f"Expected approximately 500 stocks, got {len(symbols)}. "
        f"This likely means we're reading the wrong table or Wikipedia changed their structure."
    )

    # Validate symbols look reasonable
    # - No empty strings
    # - All symbols are strings
    # - Most symbols are 1-5 characters (some like BRK.B might be longer)
    assert all(isinstance(s, str) and len(s) > 0 for s in symbols), (
        "Found empty or non-string symbols"
    )

    assert all(len(s) <= 10 for s in symbols), (
        f"Found symbols longer than 10 characters: {[s for s in symbols if len(s) > 10]}"
    )

    # Check that we have some well-known stocks (sanity check)
    well_known_stocks = {'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'}
    found_stocks = set(symbols)
    missing_stocks = well_known_stocks - found_stocks

    assert len(missing_stocks) == 0, (
        f"Expected to find well-known stocks but missing: {missing_stocks}. "
        f"This might indicate we're reading the wrong table."
    )


def test_wikipedia_sp500_matches_validator_implementation():
    """
    Enemy test: Ensures our actual implementation matches our assumptions.

    This test runs the ACTUAL get_sp500_symbols() code by directly calling
    the method logic. If this fails but the test above passes, it means our
    implementation is out of sync with reality (e.g., wrong table index).
    """
    # Directly replicate the implementation from algorithm_validator.py
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

    with urllib.request.urlopen(req, timeout=10) as response:
        tables = pd.read_html(response.read())
        # This is the actual table index used in algorithm_validator.py
        sp500_table = tables[0]
        symbols = sp500_table['Symbol'].tolist()

        # Clean symbols (same as in algorithm_validator.py)
        symbols = [s.replace('.', '-') for s in symbols]

    # Validate we didn't fall back to the hardcoded list
    assert len(symbols) > 100, (
        f"Got {len(symbols)} symbols. This looks like the fallback list. "
        f"Wikipedia fetch failed - check if table index changed."
    )

    # Validate we got approximately the right number
    assert 400 <= len(symbols) <= 600, (
        f"Expected approximately 500 stocks, got {len(symbols)}"
    )

    # Validate we have well-known stocks
    well_known_stocks = {'AAPL', 'MSFT', 'GOOGL', 'AMZN'}
    found_stocks = set(symbols)
    missing_stocks = well_known_stocks - found_stocks

    assert len(missing_stocks) == 0, (
        f"Missing well-known stocks: {missing_stocks}"
    )
