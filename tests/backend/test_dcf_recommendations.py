# ABOUTME: Tests for AI-powered DCF recommendations endpoint
# ABOUTME: Validates prompt formatting, response parsing, and caching logic

import pytest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'backend')))

from lynch_analyst import LynchAnalyst


@pytest.fixture
def sample_stock_data():
    return {
        'symbol': 'AAPL',
        'company_name': 'Apple Inc.',
        'sector': 'Technology',
        'exchange': 'NASDAQ',
        'price': 175.50,
        'pe_ratio': 28.5,
        'market_cap': 2800000000000,
        'forward_pe': 25.2,
        'forward_peg_ratio': 1.8,
        'forward_eps': 7.25
    }


@pytest.fixture
def sample_history():
    return [
        {'year': 2023, 'period': 'annual', 'free_cash_flow': 99600000000, 'revenue': 383000000000},
        {'year': 2022, 'period': 'annual', 'free_cash_flow': 111400000000, 'revenue': 394000000000},
        {'year': 2021, 'period': 'annual', 'free_cash_flow': 92900000000, 'revenue': 366000000000},
        {'year': 2020, 'period': 'annual', 'free_cash_flow': 73400000000, 'revenue': 275000000000},
        {'year': 2019, 'period': 'annual', 'free_cash_flow': 58900000000, 'revenue': 260000000000}
    ]


@pytest.fixture
def sample_wacc_data():
    return {
        'wacc': 9.5,
        'cost_of_equity': 11.2,
        'beta': 1.28,
        'after_tax_cost_of_debt': 3.5,
        'equity_weight': 85,
        'debt_weight': 15
    }


def test_generate_dcf_recommendations_valid_response(test_db, sample_stock_data, sample_history, sample_wacc_data):
    """Test that generate_dcf_recommendations returns properly structured scenarios"""
    with patch('lynch_analyst.genai.Client') as mock_client_class:
        # Setup mock response with valid JSON
        mock_response = Mock()
        mock_response.text = '''```json
{
  "scenarios": {
    "conservative": {
      "growthRate": 3,
      "terminalGrowthRate": 2,
      "discountRate": 11,
      "baseYearMethod": "avg3"
    },
    "base": {
      "growthRate": 8,
      "terminalGrowthRate": 2.5,
      "discountRate": 9.5,
      "baseYearMethod": "latest"
    },
    "optimistic": {
      "growthRate": 12,
      "terminalGrowthRate": 3,
      "discountRate": 8,
      "baseYearMethod": "latest"
    }
  },
  "reasoning": "Based on Apple's **strong FCF growth** of 14% CAGR over 5 years, the base case assumes continued momentum."
}
```'''
        mock_response.parts = [Mock()]
        
        mock_models = Mock()
        mock_models.generate_content.return_value = mock_response
        
        mock_client = Mock()
        mock_client.models = mock_models
        mock_client_class.return_value = mock_client

        analyst = LynchAnalyst(test_db, api_key="test-api-key")
        
        result = analyst.generate_dcf_recommendations(
            sample_stock_data,
            sample_history,
            wacc_data=sample_wacc_data,
            model_version="gemini-3-pro-preview"
        )

        # Verify structure
        assert 'scenarios' in result
        assert 'conservative' in result['scenarios']
        assert 'base' in result['scenarios']
        assert 'optimistic' in result['scenarios']
        assert 'reasoning' in result

        # Verify scenario values
        base = result['scenarios']['base']
        assert base['growthRate'] == 8
        assert base['discountRate'] == 9.5
        assert base['terminalGrowthRate'] == 2.5
        assert base['baseYearMethod'] == 'latest'


def test_generate_dcf_recommendations_handles_raw_json(test_db, sample_stock_data, sample_history):
    """Test that raw JSON (not in code block) is also parsed correctly"""
    with patch('lynch_analyst.genai.Client') as mock_client_class:
        mock_response = Mock()
        # Raw JSON without code block
        mock_response.text = '''{
  "scenarios": {
    "conservative": {"growthRate": 2, "terminalGrowthRate": 2, "discountRate": 12, "baseYearMethod": "avg5"},
    "base": {"growthRate": 5, "terminalGrowthRate": 2.5, "discountRate": 10, "baseYearMethod": "avg3"},
    "optimistic": {"growthRate": 10, "terminalGrowthRate": 3, "discountRate": 8, "baseYearMethod": "latest"}
  },
  "reasoning": "Analysis based on historical data."
}'''
        mock_response.parts = [Mock()]
        
        mock_models = Mock()
        mock_models.generate_content.return_value = mock_response
        
        mock_client = Mock()
        mock_client.models = mock_models
        mock_client_class.return_value = mock_client

        analyst = LynchAnalyst(test_db, api_key="test-api-key")
        
        result = analyst.generate_dcf_recommendations(
            sample_stock_data,
            sample_history,
            model_version="gemini-3-pro-preview"
        )

        assert 'scenarios' in result
        assert result['scenarios']['base']['growthRate'] == 5


def test_generate_dcf_recommendations_missing_scenario_raises(test_db, sample_stock_data, sample_history):
    """Test that missing scenarios in response raises an exception"""
    with patch('lynch_analyst.genai.Client') as mock_client_class:
        mock_response = Mock()
        # Missing 'optimistic' scenario
        mock_response.text = '''{
  "scenarios": {
    "conservative": {"growthRate": 2, "terminalGrowthRate": 2, "discountRate": 12, "baseYearMethod": "avg5"},
    "base": {"growthRate": 5, "terminalGrowthRate": 2.5, "discountRate": 10, "baseYearMethod": "avg3"}
  },
  "reasoning": "Partial response."
}'''
        mock_response.parts = [Mock()]
        
        mock_models = Mock()
        mock_models.generate_content.return_value = mock_response
        
        mock_client = Mock()
        mock_client.models = mock_models
        mock_client_class.return_value = mock_client

        analyst = LynchAnalyst(test_db, api_key="test-api-key")
        
        with pytest.raises(Exception) as exc_info:
            analyst.generate_dcf_recommendations(
                sample_stock_data,
                sample_history,
                model_version="gemini-3-pro-preview"
            )
        
        assert "optimistic" in str(exc_info.value)


def test_generate_dcf_recommendations_invalid_model_raises(test_db, sample_stock_data, sample_history):
    """Test that invalid model version raises ValueError"""
    analyst = LynchAnalyst(test_db, api_key="test-api-key")
    
    with pytest.raises(ValueError) as exc_info:
        analyst.generate_dcf_recommendations(
            sample_stock_data,
            sample_history,
            model_version="invalid-model"
        )
    
    assert "Invalid model" in str(exc_info.value)
