import pytest
import requests


@pytest.mark.skip(reason="Requires running server - convert to use Flask test client or move to e2e tests")
@pytest.mark.parametrize("algorithm", ["category_based", "classic", "weighted"])
def test_algorithm_api(algorithm):
    """Test algorithm API endpoint for AAPL with different algorithms."""
    symbol = 'AAPL'
    url = f"http://localhost:5001/api/stock/{symbol}?algorithm={algorithm}"

    response = requests.get(url, timeout=5)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    evaluation = data.get('evaluation', {})

    required_fields = [
        'symbol', 'company_name', 'country', 'market_cap', 'sector', 'ipo_year',
        'price', 'peg_ratio', 'pe_ratio', 'debt_to_equity', 'institutional_ownership',
        'dividend_yield', 'earnings_cagr', 'revenue_cagr',
        'peg_status', 'peg_score', 'debt_status', 'debt_score',
        'institutional_ownership_status', 'institutional_ownership_score',
        'overall_status'
    ]

    missing_fields = [field for field in required_fields if field not in evaluation]
    assert not missing_fields, f"Missing required fields: {missing_fields}"
    assert evaluation.get('overall_status') is not None, "overall_status should not be None"
