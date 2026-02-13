
import os
import sys
import json
import pytest
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent_tools import ToolExecutor
from database import Database

@pytest.fixture
def mock_db():
    db = MagicMock(spec=Database)
    # Mock create_strategy to return a fake ID
    db.create_strategy.return_value = 123
    return db

@pytest.fixture
def agent_tools(mock_db):
    tools = ToolExecutor(db=mock_db)
    return tools

def test_create_strategy_with_addition_thresholds(agent_tools, mock_db):
    """Test that create_strategy correctly handles addition_lynch_min and addition_buffett_min."""
    
    result = agent_tools._create_strategy(
        name="Test Strategy",
        user_id=1,
        filters=[{"field": "pe_ratio", "operator": "<", "value": 15}],
        portfolio_id="new",
        addition_lynch_min=75,
        addition_buffett_min=80
    )
    
    assert result["success"] is True
    assert result["strategy_id"] == 123
    
    # Check that create_strategy was called with correct conditions
    args, kwargs = mock_db.create_strategy.call_args
    conditions = kwargs.get('conditions')
    
    assert 'addition_scoring_requirements' in conditions
    addition_reqs = conditions['addition_scoring_requirements']
    
    lynch_req = next(r for r in addition_reqs if r['character'] == 'lynch')
    buffett_req = next(r for r in addition_reqs if r['character'] == 'buffett')
    
    assert lynch_req['min_score'] == 75
    assert buffett_req['min_score'] == 80

def test_update_strategy_with_addition_thresholds(agent_tools, mock_db):
    """Test that update_strategy correctly handles addition_lynch_min and addition_buffett_min."""
    
    # Mock existing strategy
    mock_db.get_strategy.return_value = {
        'id': 123,
        'user_id': 1,
        'name': 'Existing Strategy',
        'conditions': json.dumps({
            'filters': [],
            'addition_scoring_requirements': [
                {'character': 'lynch', 'min_score': 65},
                {'character': 'buffett', 'min_score': 65}
            ]
        })
    }
    
    result = agent_tools._update_strategy(
        strategy_id=123,
        user_id=1,
        addition_lynch_min=85
    )
    
    assert result["success"] is True
    
    # Check that update_strategy was called with correct conditions
    args, kwargs = mock_db.update_strategy.call_args
    conditions = kwargs.get('conditions')
    
    assert 'addition_scoring_requirements' in conditions
    addition_reqs = conditions['addition_scoring_requirements']
    
    lynch_req = next(r for r in addition_reqs if r['character'] == 'lynch')
    buffett_req = next(r for r in addition_reqs if r['character'] == 'buffett')
    
    assert lynch_req['min_score'] == 85
    assert buffett_req['min_score'] == 65 # Preserved existing
