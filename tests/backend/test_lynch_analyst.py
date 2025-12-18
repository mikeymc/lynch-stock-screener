# ABOUTME: Tests for LynchAnalyst class that generates Peter Lynch-style stock analyses
# ABOUTME: Validates prompt formatting, API integration, and caching logic

import pytest
import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lynch_analyst import LynchAnalyst
from database import Database

# test_db fixture is now provided by conftest.py


@pytest.fixture
def sample_stock_data():
    return {
        'symbol': 'AAPL',
        'company_name': 'Apple Inc.',
        'sector': 'Technology',
        'exchange': 'NASDAQ',
        'price': 150.25,
        'pe_ratio': 25.5,
        'peg_ratio': 1.2,
        'market_cap': 2500000000000,
        'debt_to_equity': 0.35,
        'institutional_ownership': 0.62,
        'revenue': 394000000000,
        'earnings_cagr': 15.5,
        'revenue_cagr': 12.3
    }


@pytest.fixture
def sample_history():
    return [
        {'year': 2023, 'net_income': 6130000000, 'revenue': 383000000000},
        {'year': 2022, 'net_income': 6110000000, 'revenue': 394000000000},
        {'year': 2021, 'net_income': 5610000000, 'revenue': 366000000000},
        {'year': 2020, 'net_income': 3280000000, 'revenue': 275000000000},
        {'year': 2019, 'net_income': 2970000000, 'revenue': 260000000000}
    ]


def test_lynch_analyst_initialization(test_db):
    """Test that LynchAnalyst initializes properly"""
    analyst = LynchAnalyst(test_db, api_key="test-api-key")
    assert analyst is not None
    assert analyst.db is not None


def test_format_prompt_includes_key_metrics(test_db, sample_stock_data, sample_history):
    """Test that the prompt includes all key Peter Lynch metrics"""
    analyst = LynchAnalyst(test_db, api_key="test-api-key")
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    assert 'AAPL' in prompt
    assert 'Apple Inc.' in prompt
    assert '1.2' in prompt  # PEG ratio
    assert '0.35' in prompt  # Debt/Equity
    assert '15.5' in prompt  # Earnings CAGR
    assert 'Technology' in prompt
    assert 'peter lynch' in prompt.lower()


def test_format_prompt_includes_history(test_db, sample_stock_data, sample_history):
    """Test that historical data is included in the prompt"""
    analyst = LynchAnalyst(test_db, api_key="test-api-key")
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    # Should include years
    assert '2023' in prompt
    assert '2019' in prompt

    # Should include earnings trend
    assert '6.13' in prompt
    assert '2.97' in prompt


def test_format_prompt_includes_lynch_principles(test_db, sample_stock_data, sample_history):
    """Test that Peter Lynch's key principles are referenced in the prompt"""
    analyst = LynchAnalyst(test_db, api_key="test-api-key")
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    # Should mention key Lynch concepts
    assert 'PEG' in prompt or 'price/earnings to growth' in prompt.lower()
    assert 'debt' in prompt.lower()
    assert 'earnings growth' in prompt.lower() or 'earnings' in prompt.lower()


def test_format_prompt_requests_specific_length(test_db, sample_stock_data, sample_history):
    """Test that the prompt requests 1000 word analysis"""
    analyst = LynchAnalyst(test_db, api_key="test-api-key")
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    assert '1000' in prompt


@patch('lynch_analyst.genai.Client')
def test_generate_analysis_calls_gemini_api(mock_client_class, test_db, sample_stock_data, sample_history):
    """Test that generate_analysis properly calls Gemini API"""
    # Setup mock
    mock_response = Mock()
    mock_response.text = "This is a Peter Lynch style analysis of Apple. Strong growth, reasonable valuation."
    mock_response.parts = [Mock()]  # Ensure parts exist
    
    mock_models = Mock()
    mock_models.generate_content.return_value = mock_response
    
    mock_client = Mock()
    mock_client.models = mock_models
    mock_client_class.return_value = mock_client

    # Create analyst AFTER mock is set up
    analyst = LynchAnalyst(test_db, api_key="test-api-key")

    # Generate analysis
    result = analyst.generate_analysis(sample_stock_data, sample_history, model_version="gemini-2.5-flash")

    # Verify API was called
    assert mock_models.generate_content.called
    assert result == "This is a Peter Lynch style analysis of Apple. Strong growth, reasonable valuation."


@patch('lynch_analyst.genai.Client')
def test_generate_analysis_handles_api_error(mock_client_class, test_db, sample_stock_data, sample_history):
    """Test that generate_analysis handles API errors gracefully"""
    # Setup mock to raise an error
    mock_models = Mock()
    mock_models.generate_content.side_effect = Exception("API Error")
    
    mock_client = Mock()
    mock_client.models = mock_models
    mock_client_class.return_value = mock_client

    # Create analyst AFTER mock is set up
    analyst = LynchAnalyst(test_db, api_key="test-api-key")

    # Should raise exception
    with pytest.raises(Exception):
        analyst.generate_analysis(sample_stock_data, sample_history, model_version="gemini-2.5-flash")


def test_get_or_generate_uses_cache(test_db, sample_stock_data, sample_history):
    """Test that get_or_generate_analysis uses cached analysis when available"""
    # Create analyst
    analyst = LynchAnalyst(test_db, api_key="test-api-key")
    
    # Create a test user
    user_id = test_db.create_user("google_test", "test@example.com", "Test User", None)

    # Save a cached analysis
    cached_text = "This is a cached analysis"
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock is committed before saving analysis
    test_db.save_lynch_analysis(user_id, "AAPL", cached_text, "gemini-2.5-flash")

    # Should return cached analysis without calling API
    result = analyst.get_or_generate_analysis(user_id, "AAPL", sample_stock_data, sample_history, use_cache=True, model_version="gemini-2.5-flash")

    assert result == cached_text


@patch('lynch_analyst.genai.Client')
def test_get_or_generate_bypasses_cache_when_requested(mock_client_class, test_db, sample_stock_data, sample_history):
    """Test that get_or_generate_analysis can bypass cache"""
    # Create a test user
    user_id = test_db.create_user("google_test", "test@example.com", "Test User", None)

    # Setup mock
    mock_response = Mock()
    mock_response.text = "Fresh new analysis"
    mock_response.parts = [Mock()]  # Ensure parts exist
    
    mock_models = Mock()
    mock_models.generate_content.return_value = mock_response
    
    mock_client = Mock()
    mock_client.models = mock_models
    mock_client_class.return_value = mock_client

    # Create analyst AFTER mock is set up
    analyst = LynchAnalyst(test_db, api_key="test-api-key")

    # Save a cached analysis
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock is committed before saving analysis
    test_db.save_lynch_analysis(user_id, "AAPL", "Old cached analysis", "gemini-2.5-flash")

    # Request fresh analysis
    result = analyst.get_or_generate_analysis(user_id, "AAPL", sample_stock_data, sample_history, use_cache=False, model_version="gemini-2.5-flash")

    # Should call API and return fresh analysis
    assert mock_models.generate_content.called
    assert result == "Fresh new analysis"


@patch('lynch_analyst.genai.Client')
def test_get_or_generate_saves_to_cache(mock_client_class, test_db, sample_stock_data, sample_history):
    """Test that newly generated analysis is saved to cache"""
    # Create a test user
    user_id = test_db.create_user("google_test", "test@example.com", "Test User", None)

    # Setup mock
    mock_response = Mock()
    mock_response.text = "Fresh analysis to be cached"
    mock_response.parts = [Mock()]  # Ensure parts exist
    
    mock_models = Mock()
    mock_models.generate_content.return_value = mock_response
    
    mock_client = Mock()
    mock_client.models = mock_models
    mock_client_class.return_value = mock_client

    # Create analyst AFTER mock is set up
    analyst = LynchAnalyst(test_db, api_key="test-api-key")

    # Generate analysis
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.flush()  # Ensure stock is committed before saving analysis
    result = analyst.get_or_generate_analysis(user_id, "AAPL", sample_stock_data, sample_history, use_cache=False, model_version="gemini-2.5-flash")

    # Verify it was saved to database
    cached = test_db.get_lynch_analysis(user_id, "AAPL")
    assert cached is not None
    assert cached['analysis_text'] == "Fresh analysis to be cached"
