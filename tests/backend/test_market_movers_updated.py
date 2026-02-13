import pytest
import pandas as pd
from app import app, deps
from unittest.mock import MagicMock, patch

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Ensure deps are available in the test environment
    # Note: app factory initializes them, but we might need to mock them if they fail
    with app.test_client() as client:
        yield client

def test_get_market_movers_vectorized(client):
    """Test that market movers endpoint uses vectorized scoring and returns correct fields."""
    
    # Mock data for StockVectors
    mock_df = pd.DataFrame([
        {
            'symbol': 'AAPL', 
            'company_name': 'Apple Inc.', 
            'price': 150.0, 
            'price_change_pct': 5.0, 
            'pe_ratio': 25.0,
            'overall_score': 85.0,
            'overall_status': 'STRONG_BUY'
        },
        {
            'symbol': 'MSFT', 
            'company_name': 'Microsoft', 
            'price': 250.0, 
            'price_change_pct': -2.0, 
            'pe_ratio': 30.0,
            'overall_score': 75.0,
            'overall_status': 'BUY'
        },
        {
            'symbol': 'CAUT', 
            'company_name': 'Caution Stock', 
            'price': 10.0, 
            'price_change_pct': 10.0, 
            'pe_ratio': 100.0,
            'overall_score': 30.0,
            'overall_status': 'CAUTION'
        }
    ])
    
    # Mock the services in deps
    with patch('app.deps.stock_vectors.load_vectors') as mock_load, \
         patch('app.deps.criteria.evaluate_batch') as mock_eval:
        
        mock_load.return_value = mock_df
        # Mock evaluate_batch to return the same DF (or just the quality ones)
        # In reality it adds scores based on config, but for testing we mock it
        mock_eval.return_value = mock_df
        
        # Also mock db to avoid auth/config issues if any
        with patch('app.deps.db.get_user_character') as mock_char, \
             patch('app.deps.db.get_algorithm_configs') as mock_configs:
            
            mock_char.return_value = 'lynch'
            mock_configs.return_value = [] # Empty list will trigger default config
            
            response = client.get('/api/market/movers?period=1d&limit=5')
        
    assert response.status_code == 200
    data = response.get_json()
    
    assert 'gainers' in data
    assert 'losers' in data
    
    # Check Gainers (AAPL should be first, CAUT should be excluded)
    assert len(data['gainers']) == 1 # Only AAPL is quality and positive
    assert data['gainers'][0]['symbol'] == 'AAPL'
    assert data['gainers'][0]['pe_ratio'] == 25.0
    assert data['gainers'][0]['overall_score'] == 85.0
    assert data['gainers'][0]['overall_status'] == 'STRONG_BUY'
    
    # Check Losers (MSFT is quality and negative)
    assert len(data['losers']) == 1
    assert data['losers'][0]['symbol'] == 'MSFT'
    assert data['losers'][0]['change_pct'] == -2.0
    
    # Verify CAUT was excluded despite 10% gain because it's CAUTION status
    for g in data['gainers']:
        assert g['symbol'] != 'CAUT'

def test_get_market_movers_historical(client):
    """Test market movers with a historical period (e.g., 1w)."""
    
    mock_df = pd.DataFrame([
        {'symbol': 'AAPL', 'company_name': 'Apple', 'price': 150.0, 'pe_ratio': 25.0, 'overall_score': 80.0, 'overall_status': 'BUY'},
        {'symbol': 'MSFT', 'company_name': 'Microsoft', 'price': 250.0, 'pe_ratio': 30.0, 'overall_score': 70.0, 'overall_status': 'BUY'}
    ])
    
    with patch('app.deps.stock_vectors.load_vectors') as mock_load, \
         patch('app.deps.criteria.evaluate_batch') as mock_eval, \
         patch('app.deps.db.get_connection') as mock_get_conn:
        
        mock_load.return_value = mock_df
        mock_eval.return_value = mock_df
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock historical prices
        mock_cursor.fetchall.return_value = [
            {'symbol': 'AAPL', 'historical_price': 140.0}, # +7.14%
            {'symbol': 'MSFT', 'historical_price': 260.0}  # -3.85%
        ]
        
        with patch('app.deps.db.return_connection'), \
             patch('app.deps.db.get_user_character', return_value='lynch'):
            response = client.get('/api/market/movers?period=1w&limit=5')
            
    assert response.status_code == 200
    data = response.get_json()
    
    assert len(data['gainers']) == 1
    assert data['gainers'][0]['symbol'] == 'AAPL'
    # 150/140 - 1 = 0.0714 -> 7.14%
    assert round(data['gainers'][0]['change_pct'], 2) == 7.14
    
    assert len(data['losers']) == 1
    assert data['losers'][0]['symbol'] == 'MSFT'
    # 250/260 - 1 = -0.0384 -> -3.85%
    assert round(data['losers'][0]['change_pct'], 2) == -3.85
