import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from schwab_client import SchwabClient


def test_schwab_client_initializes_without_credentials():
    """Test that SchwabClient can be initialized even without credentials"""
    with patch.dict('os.environ', {}, clear=True):
        client = SchwabClient()
        assert client.api_key is None
        assert client.api_secret is None
        assert not client.is_available()


def test_schwab_client_initializes_with_credentials():
    """Test that SchwabClient reads credentials from environment"""
    with patch.dict('os.environ', {
        'SCHWAB_API_KEY': 'test_key',
        'SCHWAB_API_SECRET': 'test_secret',
        'SCHWAB_REDIRECT_URI': 'https://localhost',
        'SCHWAB_TOKEN_PATH': './test_tokens.json'
    }):
        client = SchwabClient()
        assert client.api_key == 'test_key'
        assert client.api_secret == 'test_secret'
        assert client.redirect_uri == 'https://localhost'
        assert client.token_path == './test_tokens.json'
        assert client.is_available()


def test_schwab_authentication_fails_without_credentials():
    """Test that authentication fails when credentials are missing"""
    with patch.dict('os.environ', {}, clear=True):
        client = SchwabClient()
        result = client.authenticate()
        assert result is False
        assert not client._authenticated


def test_get_historical_price_returns_none_when_not_authenticated():
    """Test that get_historical_price returns None when not authenticated"""
    with patch.dict('os.environ', {}, clear=True):
        client = SchwabClient()
        price = client.get_historical_price("AAPL", "2023-09-30")
        assert price is None


def test_get_historical_price_with_invalid_date():
    """Test that get_historical_price handles invalid date format"""
    with patch.dict('os.environ', {
        'SCHWAB_API_KEY': 'test_key',
        'SCHWAB_API_SECRET': 'test_secret'
    }):
        client = SchwabClient()
        client._authenticated = True  # Bypass authentication

        price = client.get_historical_price("AAPL", "invalid-date")
        assert price is None


@patch('schwab_client.SchwabClient.authenticate')
def test_get_historical_price_authenticates_if_needed(mock_auth):
    """Test that get_historical_price calls authenticate if not authenticated"""
    mock_auth.return_value = False

    with patch.dict('os.environ', {
        'SCHWAB_API_KEY': 'test_key',
        'SCHWAB_API_SECRET': 'test_secret'
    }):
        client = SchwabClient()
        price = client.get_historical_price("AAPL", "2023-09-30")

        mock_auth.assert_called_once()
        assert price is None  # Because auth failed
