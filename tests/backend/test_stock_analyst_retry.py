# ABOUTME: Tests for StockAnalyst retry logic with Gemini API failures
# ABOUTME: Verifies exponential backoff and model fallback behavior

import pytest
import unittest.mock as mock
import time
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def mock_db():
    """Mock database for StockAnalyst tests."""
    db = MagicMock()
    db.get_setting.return_value = 'lynch'
    db.get_user_character.return_value = 'lynch'
    return db


@pytest.fixture
def stock_analyst(mock_db):
    """Create StockAnalyst instance with mocked dependencies."""
    from stock_analyst import StockAnalyst

    with patch('stock_analyst.core.genai.Client') as mock_client_class:
        analyst = StockAnalyst(mock_db, api_key='test_key')
        # Mock the client property
        analyst._client = MagicMock()
        yield analyst


@pytest.fixture
def sample_stock_data():
    """Sample stock data for analysis generation."""
    return {
        'symbol': 'AAPL',
        'company_name': 'Apple Inc.',
        'sector': 'Technology',
        'exchange': 'NASDAQ',
        'price': 180.00,
        'pe_ratio': 30.0,
        'peg_ratio': 1.5,
        'debt_to_equity': 150.0,
        'institutional_ownership': 0.60,
        'market_cap': 3000000000000,
        'earnings_cagr': 0.15,
        'revenue_cagr': 0.10
    }


@pytest.fixture
def sample_history():
    """Sample financial history data."""
    return [
        {
            'year': 2023,
            'period': 'annual',
            'net_income': 100000000000,
            'revenue': 400000000000,
            'operating_cash_flow': 120000000000,
            'capital_expenditures': -10000000000,
            'free_cash_flow': 110000000000
        }
    ]


class Test503RetryLogic:
    """Test retry logic for 503 errors during streaming generation."""

    def test_generate_analysis_stream_retries_on_503(self, stock_analyst, sample_stock_data, sample_history):
        """Test that generate_analysis_stream retries on 503 errors with exponential backoff."""
        # Mock the streaming response to fail twice with 503, then succeed
        mock_stream = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.text = 'Test analysis content'
        mock_stream.__iter__ = MagicMock(return_value=iter([mock_chunk]))

        # First two calls raise 503, third succeeds
        stock_analyst.client.models.generate_content_stream.side_effect = [
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),
            mock_stream
        ]

        with patch('time.sleep') as mock_sleep:
            # Generate analysis
            result = list(stock_analyst.generate_analysis_stream(
                sample_stock_data,
                sample_history,
                model_version='gemini-3-pro-preview'
            ))

            # Verify it retried 3 times total (2 failures + 1 success)
            assert stock_analyst.client.models.generate_content_stream.call_count == 3

            # Verify exponential backoff was used: 1s, 2s
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(1)  # First retry: 1s
            mock_sleep.assert_any_call(2)  # Second retry: 2s

            # Verify we got the successful result
            assert result == ['Test analysis content']

    def test_generate_analysis_stream_falls_back_to_flash(self, stock_analyst, sample_stock_data, sample_history):
        """Test that generate_analysis_stream falls back from pro to flash after max retries."""
        # Mock to fail 3 times with pro, then succeed with flash
        mock_stream = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.text = 'Fallback analysis content'
        mock_stream.__iter__ = MagicMock(return_value=iter([mock_chunk]))

        # Fail 4 times (max retries for pro), then succeed with flash
        stock_analyst.client.models.generate_content_stream.side_effect = [
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),  # 4th failure triggers fallback
            mock_stream  # Flash succeeds
        ]

        with patch('time.sleep'):
            result = list(stock_analyst.generate_analysis_stream(
                sample_stock_data,
                sample_history,
                model_version='gemini-3-pro-preview'
            ))

            # Verify it tried pro 4 times, then flash once
            assert stock_analyst.client.models.generate_content_stream.call_count == 5

            # Verify first 4 calls used pro, last call used flash
            calls = stock_analyst.client.models.generate_content_stream.call_args_list
            assert calls[0].kwargs['model'] == 'gemini-3-pro-preview'
            assert calls[1].kwargs['model'] == 'gemini-3-pro-preview'
            assert calls[2].kwargs['model'] == 'gemini-3-pro-preview'
            assert calls[3].kwargs['model'] == 'gemini-3-pro-preview'
            assert calls[4].kwargs['model'] == 'gemini-2.5-flash'

            # Verify we got the successful result
            assert result == ['Fallback analysis content']

    def test_generate_analysis_stream_raises_after_all_retries_exhausted(self, stock_analyst, sample_stock_data, sample_history):
        """Test that generate_analysis_stream raises exception after all retries exhausted."""
        # Mock to fail all attempts
        stock_analyst.client.models.generate_content_stream.side_effect = Exception("503 Service Unavailable")

        with patch('time.sleep'):
            with pytest.raises(Exception, match="503"):
                list(stock_analyst.generate_analysis_stream(
                    sample_stock_data,
                    sample_history,
                    model_version='gemini-3-pro-preview'
                ))

            # Should try pro 4 times (initial + 3 retries), then flash 4 times
            # Total: 8 attempts
            assert stock_analyst.client.models.generate_content_stream.call_count == 8


class Test503RetryLogicChartNarrative:
    """Test retry logic for 503 errors during chart narrative generation."""

    def test_generate_unified_chart_analysis_retries_on_503(self, stock_analyst, sample_stock_data, sample_history):
        """Test that generate_unified_chart_analysis retries on 503 errors."""
        # Mock the response to fail twice with 503, then succeed
        mock_response = MagicMock()
        mock_response.parts = [MagicMock()]
        mock_response.text = 'Chart narrative content'

        # First two calls raise 503, third succeeds
        stock_analyst.client.models.generate_content.side_effect = [
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),
            mock_response
        ]

        with patch('time.sleep') as mock_sleep:
            result = stock_analyst.generate_unified_chart_analysis(
                sample_stock_data,
                sample_history,
                model_version='gemini-3-pro-preview'
            )

            # Verify it retried 3 times total
            assert stock_analyst.client.models.generate_content.call_count == 3

            # Verify exponential backoff
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(1)
            mock_sleep.assert_any_call(2)

            # Verify result
            assert result == {'narrative': 'Chart narrative content'}

    def test_generate_unified_chart_analysis_falls_back_to_flash(self, stock_analyst, sample_stock_data, sample_history):
        """Test that generate_unified_chart_analysis falls back to flash model."""
        mock_response = MagicMock()
        mock_response.parts = [MagicMock()]
        mock_response.text = 'Fallback chart narrative'

        # Fail 4 times with pro, succeed with flash
        stock_analyst.client.models.generate_content.side_effect = [
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),
            Exception("503 Service Unavailable"),
            mock_response
        ]

        with patch('time.sleep'):
            result = stock_analyst.generate_unified_chart_analysis(
                sample_stock_data,
                sample_history,
                model_version='gemini-3-pro-preview'
            )

            # Verify fallback occurred
            assert stock_analyst.client.models.generate_content.call_count == 5

            # Verify models used
            calls = stock_analyst.client.models.generate_content.call_args_list
            assert calls[0].kwargs['model'] == 'gemini-3-pro-preview'
            assert calls[4].kwargs['model'] == 'gemini-2.5-flash'

            assert result == {'narrative': 'Fallback chart narrative'}


class TestOverloadedError:
    """Test retry logic specifically for 'overloaded' error messages."""

    def test_retries_on_overloaded_error_message(self, stock_analyst, sample_stock_data, sample_history):
        """Test that retry occurs when error message contains 'overloaded'."""
        mock_stream = MagicMock()
        mock_chunk = MagicMock()
        mock_chunk.text = 'Success after overload'
        mock_stream.__iter__ = MagicMock(return_value=iter([mock_chunk]))

        stock_analyst.client.models.generate_content_stream.side_effect = [
            Exception("Model is currently overloaded. Please try again."),
            mock_stream
        ]

        with patch('time.sleep') as mock_sleep:
            result = list(stock_analyst.generate_analysis_stream(
                sample_stock_data,
                sample_history,
                model_version='gemini-3-pro-preview'
            ))

            assert stock_analyst.client.models.generate_content_stream.call_count == 2
            mock_sleep.assert_called_once_with(1)
            assert result == ['Success after overload']


class TestNonRetriableErrors:
    """Test that non-retriable errors fail immediately without retries."""

    def test_non_503_error_fails_immediately(self, stock_analyst, sample_stock_data, sample_history):
        """Test that non-503 errors don't trigger retries."""
        stock_analyst.client.models.generate_content_stream.side_effect = Exception("Invalid API key")

        with patch('time.sleep') as mock_sleep:
            with pytest.raises(Exception, match="Invalid API key"):
                list(stock_analyst.generate_analysis_stream(
                    sample_stock_data,
                    sample_history,
                    model_version='gemini-3-pro-preview'
                ))

            # Should only try once (no retries for non-503 errors)
            assert stock_analyst.client.models.generate_content_stream.call_count == 1
            # Should not sleep (no retries)
            assert mock_sleep.call_count == 0
