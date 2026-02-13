import pytest
from unittest.mock import MagicMock
from strategy_executor.universe_filter import UniverseFilter

@pytest.fixture
def mock_db_tuple():
    db = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    
    db.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Mock symbols
    mock_cursor.fetchall.side_effect = [
        [('AAPL',), ('MSFT',), ('TSLA',)], # initial symbols
        [('AAPL',), ('MSFT',)],             # first filter
        [('AAPL',)]                         # second filter
    ]
    return db, mock_cursor

def test_universe_filter_dividend_yield(mock_db_tuple):
    mock_db, mock_cursor = mock_db_tuple
    uf = UniverseFilter(mock_db)
    
    conditions = {
        'universe': {
            'filters': [
                {'field': 'dividend_yield', 'operator': '>', 'value': 3.0}
            ]
        }
    }
    
    mock_cursor.fetchall.side_effect = [[('AAPL',), ('T',)], [('T',)]]
    symbols = uf.filter_universe(conditions)
    
    # Verify SQL calls
    calls = mock_cursor.execute.call_args_list
    
    found_dividend_yield = False
    for call in calls:
        query = call[0][0]
        if 'dividend_yield > %s' in query:
            found_dividend_yield = True
            
    assert found_dividend_yield
    assert 'T' in symbols

def test_peg_ratio_mapping(mock_db_tuple):
    mock_db, mock_cursor = mock_db_tuple
    uf = UniverseFilter(mock_db)
    
    conditions = {
        'universe': {
            'filters': [
                {'field': 'peg_ratio', 'operator': '<=', 'value': 1.0}
            ]
        }
    }
    
    mock_cursor.fetchall.side_effect = [[('AAPL',)], [('AAPL',)]]
    uf.filter_universe(conditions)
    
    calls = mock_cursor.execute.call_args_list
    found_forward_peg = False
    for call in calls:
        query = call[0][0]
        if 'forward_peg_ratio <= %s' in query:
            found_forward_peg = True
            
    assert found_forward_peg
    
def test_price_52w_fallback(mock_db_tuple):
    mock_db, mock_cursor = mock_db_tuple
    uf = UniverseFilter(mock_db)
    
    conditions = {
        'universe': {
            'filters': [
                {'field': 'price_vs_52wk_high', 'operator': '<=', 'value': -20}
            ]
        }
    }
    
    mock_cursor.fetchall.side_effect = [[('AAPL',)], [('AAPL',)]]
    uf.filter_universe(conditions)
    
    calls = mock_cursor.execute.call_args_list
    found_price_change_pct = False
    for call in calls:
        query = call[0][0]
        if 'price_change_pct <= %s' in query:
            found_price_change_pct = True
            
    assert found_price_change_pct
