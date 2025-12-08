"""
Pytest fixtures for backend unit and integration tests.
"""

import sys
import os
import pytest

# Add backend directory to Python path for imports
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
sys.path.insert(0, os.path.abspath(backend_path))


@pytest.fixture(scope="function")
def test_client(test_database):
    """Create Flask test client with test database.

    Note: test_database fixture is defined in tests/conftest.py (shared)
    """
    # Set test database environment variables BEFORE importing app
    os.environ['DB_NAME'] = test_database
    os.environ['DB_HOST'] = 'localhost'
    os.environ['DB_PORT'] = '5432'
    os.environ['DB_USER'] = 'lynch'
    os.environ['DB_PASSWORD'] = 'lynch_dev_password'

    # Import app AFTER setting env vars
    # This ensures app.py uses test database
    from app import app
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client


@pytest.fixture(scope="function")
def mock_yfinance():
    """Mock yfinance to avoid external API calls in tests."""
    import unittest.mock as mock

    with mock.patch('yfinance.Ticker') as mock_ticker:
        # Create a mock ticker instance with realistic data
        mock_instance = mock.MagicMock()

        # Mock info property with realistic stock data
        mock_instance.info = {
            'symbol': 'AAPL',
            'shortName': 'Apple Inc.',
            'country': 'United States',
            'marketCap': 3000000000000,  # $3T
            'sector': 'Technology',
            'regularMarketPrice': 180.00,
            'currentPrice': 180.00,
            'trailingPE': 30.0,
            'forwardPE': 28.0,
            'debtToEquity': 150.0,
            'trailingEps': 6.00
        }

        # Mock fast_info property (used by some data fetchers)
        mock_fast_info = mock.MagicMock()
        mock_fast_info.last_price = 180.00
        mock_fast_info.market_cap = 3000000000000
        mock_instance.fast_info = mock_fast_info

        mock_ticker.return_value = mock_instance
        yield mock_ticker


def pytest_collection_modifyitems(items):
    """Automatically add 'backend' marker to all tests in this directory."""
    for item in items:
        if "tests/backend" in str(item.fspath):
            item.add_marker(pytest.mark.backend)
