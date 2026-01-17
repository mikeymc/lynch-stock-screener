import pytest


@pytest.mark.parametrize("algorithm", ["weighted"])
def test_algorithm_api(test_client, mock_yfinance, algorithm):
    """Test algorithm API endpoint with different algorithms using Flask test client."""
    symbol = 'AAPL'

    # Call endpoint via Flask test client (no HTTP server needed)
    response = test_client.get(f'/api/stock/{symbol}?algorithm={algorithm}')

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.data}"

    data = response.json
    assert 'evaluation' in data, "Response missing 'evaluation' field"
    assert 'stock_data' in data, "Response missing 'stock_data' field"

    evaluation = data['evaluation']

    # Verify all required fields are present
    required_fields = [
        'symbol', 'company_name', 'country', 'market_cap', 'sector', 'ipo_year',
        'price', 'peg_ratio', 'pe_ratio', 'debt_to_equity', 'institutional_ownership',
        'dividend_yield', 'earnings_cagr', 'revenue_cagr',
        'peg_status', 'peg_score', 'debt_status', 'debt_score',
        'institutional_ownership_status', 'institutional_ownership_score',
        'overall_status', 'overall_score'
    ]

    missing_fields = [field for field in required_fields if field not in evaluation]
    assert not missing_fields, f"Missing required fields: {missing_fields}"

    # Verify critical fields have valid values
    assert evaluation.get('overall_status') is not None, "overall_status should not be None"
    assert evaluation.get('overall_score') is not None, "overall_score should not be None"
    assert isinstance(evaluation['overall_score'], (int, float)), "overall_score should be numeric"

    # Verify algorithm-specific behavior
    # All algorithms should return same fields but potentially different scores
    assert evaluation['symbol'] == symbol, f"Expected symbol {symbol}, got {evaluation['symbol']}"
