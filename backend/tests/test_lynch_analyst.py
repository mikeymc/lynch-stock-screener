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
def analyst(test_db):
    return LynchAnalyst(test_db, api_key="test-api-key")


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
        {'year': 2023, 'eps': 6.13, 'revenue': 383000000000},
        {'year': 2022, 'eps': 6.11, 'revenue': 394000000000},
        {'year': 2021, 'eps': 5.61, 'revenue': 366000000000},
        {'year': 2020, 'eps': 3.28, 'revenue': 275000000000},
        {'year': 2019, 'eps': 2.97, 'revenue': 260000000000}
    ]


def test_lynch_analyst_initialization(analyst):
    """Test that LynchAnalyst initializes properly"""
    assert analyst is not None
    assert analyst.db is not None
    assert analyst.model_version == "gemini-3-pro" #"gemini-2.5-flash"


def test_format_prompt_includes_key_metrics(analyst, sample_stock_data, sample_history):
    """Test that the prompt includes all key Peter Lynch metrics"""
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    assert 'AAPL' in prompt
    assert 'Apple Inc.' in prompt
    assert '1.2' in prompt  # PEG ratio
    assert '0.35' in prompt  # Debt/Equity
    assert '15.5' in prompt  # Earnings CAGR
    assert 'Technology' in prompt
    assert 'peter lynch' in prompt.lower()


def test_format_prompt_includes_history(analyst, sample_stock_data, sample_history):
    """Test that historical data is included in the prompt"""
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    # Should include years
    assert '2023' in prompt
    assert '2019' in prompt

    # Should include earnings trend
    assert '6.13' in prompt
    assert '2.97' in prompt


def test_format_prompt_includes_lynch_principles(analyst, sample_stock_data, sample_history):
    """Test that Peter Lynch's key principles are referenced in the prompt"""
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    # Should mention key Lynch concepts
    assert 'PEG' in prompt or 'price/earnings to growth' in prompt.lower()
    assert 'debt' in prompt.lower()
    assert 'earnings growth' in prompt.lower() or 'earnings' in prompt.lower()


def test_format_prompt_requests_specific_length(analyst, sample_stock_data, sample_history):
    """Test that the prompt requests 1000 word analysis"""
    prompt = analyst.format_prompt(sample_stock_data, sample_history)

    assert '1000' in prompt


@patch('google.generativeai.GenerativeModel')
def test_generate_analysis_calls_gemini_api(mock_model_class, analyst, sample_stock_data, sample_history):
    """Test that generate_analysis properly calls Gemini API"""
    # Setup mock
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = "This is a Peter Lynch style analysis of Apple. Strong growth, reasonable valuation."
    mock_model.generate_content.return_value = mock_response
    mock_model_class.return_value = mock_model

    # Generate analysis
    result = analyst.generate_analysis(sample_stock_data, sample_history)

    # Verify API was called
    assert mock_model.generate_content.called
    assert result == "This is a Peter Lynch style analysis of Apple. Strong growth, reasonable valuation."


@patch('google.generativeai.GenerativeModel')
def test_generate_analysis_handles_api_error(mock_model_class, analyst, sample_stock_data, sample_history):
    """Test that generate_analysis handles API errors gracefully"""
    # Setup mock to raise an error
    mock_model = Mock()
    mock_model.generate_content.side_effect = Exception("API Error")
    mock_model_class.return_value = mock_model

    # Should raise exception
    with pytest.raises(Exception):
        analyst.generate_analysis(sample_stock_data, sample_history)


def test_get_or_generate_uses_cache(analyst, test_db, sample_stock_data, sample_history):
    """Test that get_or_generate_analysis uses cached analysis when available"""
    # Save a cached analysis
    cached_text = "This is a cached analysis"
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_lynch_analysis("AAPL", cached_text, "gemini-3-pro-preview")

    # Should return cached analysis without calling API
    result = analyst.get_or_generate_analysis("AAPL", sample_stock_data, sample_history, use_cache=True)

    assert result == cached_text


@patch('google.generativeai.GenerativeModel')
def test_get_or_generate_bypasses_cache_when_requested(mock_model_class, analyst, test_db, sample_stock_data, sample_history):
    """Test that get_or_generate_analysis can bypass cache"""
    # Setup mock
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = "Fresh new analysis"
    mock_model.generate_content.return_value = mock_response
    mock_model_class.return_value = mock_model

    # Save a cached analysis
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    test_db.save_lynch_analysis("AAPL", "Old cached analysis", "gemini-pro")

    # Request fresh analysis
    result = analyst.get_or_generate_analysis("AAPL", sample_stock_data, sample_history, use_cache=False)

    # Should call API and return fresh analysis
    assert mock_model.generate_content.called
    assert result == "Fresh new analysis"


@patch('google.generativeai.GenerativeModel')
def test_get_or_generate_saves_to_cache(mock_model_class, analyst, test_db, sample_stock_data, sample_history):
    """Test that newly generated analysis is saved to cache"""
    # Setup mock
    mock_model = Mock()
    mock_response = Mock()
    mock_response.text = "Fresh analysis to be cached"
    mock_model.generate_content.return_value = mock_response
    mock_model_class.return_value = mock_model

    # Generate analysis
    test_db.save_stock_basic("AAPL", "Apple Inc.", "NASDAQ", "Technology")
    result = analyst.get_or_generate_analysis("AAPL", sample_stock_data, sample_history, use_cache=False)

    # Verify it was saved to database
    cached = test_db.get_lynch_analysis("AAPL")
    assert cached is not None
    assert cached['analysis_text'] == "Fresh analysis to be cached"
