# ABOUTME: Tests for BriefingGenerator which assembles structured data and generates AI summaries
# ABOUTME: Verifies data assembly from decisions and mocks the Gemini API call

import pytest
import json
from unittest.mock import patch, MagicMock
from strategy_executor.briefing import BriefingGenerator


@pytest.fixture
def mock_db():
    """Mock database with run decisions and performance data."""
    db = MagicMock()

    db.get_strategy_run.return_value = {
        'id': 1,
        'strategy_id': 10,
        'stocks_screened': 500,
        'stocks_scored': 25,
        'theses_generated': 10,
        'trades_executed': 3,
        'portfolio_value': 102500.0,
    }

    db.get_run_decisions.return_value = [
        {
            'symbol': 'AAPL',
            'final_decision': 'BUY',
            'decision_reasoning': 'Strong earnings growth',
            'shares_traded': 10,
            'trade_price': 180.0,
            'thesis_verdict': 'BUY',
            'thesis_summary': 'Apple shows strong fundamentals.',
            'thesis_full': 'Lynch sees Apple as a stalwart with consistent 15% earnings growth. Buffett agrees the brand moat is wide.',
            'lynch_score': 82.5,
            'buffett_score': 78.0,
            'lynch_status': 'excellent',
            'buffett_status': 'good',
            'consensus_verdict': 'BUY',
            'consensus_score': 80.2,
            'dcf_fair_value': 210.0,
            'dcf_upside_pct': 16.7,
            'position_value': 1800.0,
        },
        {
            'symbol': 'GOOGL',
            'final_decision': 'BUY',
            'decision_reasoning': 'Undervalued relative to peers',
            'shares_traded': 5,
            'trade_price': 140.0,
            'thesis_verdict': 'BUY',
            'thesis_summary': 'Google remains dominant.',
            'thesis_full': 'Lynch classifies Google as a fast grower with search monopoly. Buffett likes the capital-light model.',
            'lynch_score': 76.0,
            'buffett_score': 81.0,
            'lynch_status': 'good',
            'buffett_status': 'excellent',
            'consensus_verdict': 'BUY',
            'consensus_score': 78.5,
            'dcf_fair_value': 165.0,
            'dcf_upside_pct': 17.9,
            'position_value': 700.0,
        },
        {
            'symbol': 'MSFT',
            'final_decision': 'HOLD',
            'decision_reasoning': 'Still meets criteria',
            'shares_traded': None,
            'trade_price': None,
            'thesis_verdict': 'WATCH',
            'thesis_summary': 'Microsoft is fairly valued.',
            'thesis_full': 'Lynch notes slowing growth but steady dividends. Buffett sees a durable competitive advantage in cloud.',
            'lynch_score': 65.0,
            'buffett_score': 72.0,
            'lynch_status': 'good',
            'buffett_status': 'good',
            'consensus_verdict': 'WATCH',
            'consensus_score': 68.5,
            'dcf_fair_value': 380.0,
            'dcf_upside_pct': 5.2,
            'position_value': 3600.0,
        },
        {
            'symbol': 'INTC',
            'final_decision': 'SELL',
            'decision_reasoning': 'Score degradation below threshold',
            'shares_traded': 20,
            'trade_price': 35.0,
            'thesis_verdict': 'AVOID',
            'thesis_summary': 'Intel facing headwinds.',
            'thesis_full': 'Lynch flags the turnaround as too uncertain. Buffett warns about capital intensity destroying returns.',
            'lynch_score': 35.0,
            'buffett_score': 28.0,
            'lynch_status': 'poor',
            'buffett_status': 'poor',
            'consensus_verdict': 'AVOID',
            'consensus_score': 31.5,
            'dcf_fair_value': 30.0,
            'dcf_upside_pct': -14.3,
            'position_value': 700.0,
        },
    ]

    return db


@pytest.fixture
def performance_data():
    return {
        'portfolio_value': 102500.0,
        'portfolio_return_pct': 2.5,
        'spy_return_pct': 1.2,
        'alpha': 1.3,
    }


def test_assemble_structured_data(mock_db, performance_data):
    """Test that structured data is correctly assembled from decisions."""
    generator = BriefingGenerator(mock_db)

    with patch.object(generator, '_generate_executive_summary', return_value='Test summary.'):
        result = generator.generate(
            run_id=1,
            strategy_id=10,
            portfolio_id=100,
            performance=performance_data,
        )

    assert result['stocks_screened'] == 500
    assert result['stocks_scored'] == 25
    assert result['trades_executed'] == 3

    buys = json.loads(result['buys_json'])
    assert len(buys) == 2
    assert buys[0]['symbol'] == 'AAPL'
    assert buys[0]['shares'] == 10
    assert buys[0]['price'] == 180.0
    # Enriched fields
    assert buys[0]['lynch_score'] == 82.5
    assert buys[0]['buffett_score'] == 78.0
    assert buys[0]['consensus_verdict'] == 'BUY'
    assert buys[0]['dcf_fair_value'] == 210.0
    assert buys[0]['dcf_upside_pct'] == 16.7
    assert 'stalwart' in buys[0]['deliberation']

    sells = json.loads(result['sells_json'])
    assert len(sells) == 1
    assert sells[0]['symbol'] == 'INTC'
    assert sells[0]['lynch_score'] == 35.0
    assert sells[0]['consensus_verdict'] == 'AVOID'
    assert 'turnaround' in sells[0]['deliberation']

    holds = json.loads(result['holds_json'])
    assert len(holds) == 1
    assert holds[0]['symbol'] == 'MSFT'
    assert holds[0]['lynch_score'] == 65.0
    assert holds[0]['consensus_verdict'] == 'WATCH'


def test_generate_calls_gemini(mock_db, performance_data):
    """Test that executive summary is generated via Gemini."""
    generator = BriefingGenerator(mock_db)

    mock_response = MagicMock()
    mock_response.text = 'AI-generated executive summary of the run.'

    with patch('strategy_executor.briefing.genai') as mock_genai:
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.return_value = mock_response

        result = generator.generate(
            run_id=1,
            strategy_id=10,
            portfolio_id=100,
            performance=performance_data,
        )

    assert result['executive_summary'] == 'AI-generated executive summary of the run.'
    mock_client.models.generate_content.assert_called_once()


def test_generate_handles_gemini_failure(mock_db, performance_data):
    """Test that briefing is still created when Gemini fails."""
    generator = BriefingGenerator(mock_db)

    with patch('strategy_executor.briefing.genai') as mock_genai:
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception('API error')

        result = generator.generate(
            run_id=1,
            strategy_id=10,
            portfolio_id=100,
            performance=performance_data,
        )

    # Should still return a briefing, just without AI summary
    assert result['run_id'] == 1
    assert result['stocks_screened'] == 500
    assert 'unable to generate' in result['executive_summary'].lower() or result['executive_summary'] != ''


def test_generate_with_no_trades(mock_db, performance_data):
    """Test briefing generation when there are no trades."""
    mock_db.get_run_decisions.return_value = [
        {
            'symbol': 'MSFT',
            'final_decision': 'SKIP',
            'decision_reasoning': 'Does not meet criteria',
            'shares_traded': None,
            'trade_price': None,
            'thesis_verdict': 'WATCH',
            'thesis_summary': 'Watchlist candidate.',
            'thesis_full': None,
            'lynch_score': 45.0,
            'buffett_score': 50.0,
            'lynch_status': 'fair',
            'buffett_status': 'fair',
            'consensus_verdict': 'WATCH',
            'consensus_score': 47.5,
            'dcf_fair_value': None,
            'dcf_upside_pct': None,
            'position_value': None,
        },
    ]
    mock_db.get_strategy_run.return_value['trades_executed'] = 0

    generator = BriefingGenerator(mock_db)

    with patch.object(generator, '_generate_executive_summary', return_value='No trades today.'):
        result = generator.generate(
            run_id=1,
            strategy_id=10,
            portfolio_id=100,
            performance=performance_data,
        )

    buys = json.loads(result['buys_json'])
    sells = json.loads(result['sells_json'])
    assert len(buys) == 0
    assert len(sells) == 0
