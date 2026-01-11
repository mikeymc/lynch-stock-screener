
import pytest
from unittest.mock import MagicMock, patch
import json
import datetime


# Mock database connection for testing
import sys
import os
from unittest.mock import MagicMock

# Add backend directory to path so imports like 'from price_history_fetcher' work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock google.genai specifically
mock_genai = MagicMock()
sys.modules["google.genai"] = mock_genai
sys.modules["google.genai.types"] = MagicMock()

# Mock all fetcher dependencies to allow worker.py import
sys.modules["price_history_fetcher"] = MagicMock()
sys.modules["sec_data_fetcher"] = MagicMock()
sys.modules["news_fetcher"] = MagicMock()
sys.modules["material_events_fetcher"] = MagicMock()
sys.modules["sec_rate_limiter"] = MagicMock()
# Mock yfinance cache which is imported early in worker.py
sys.modules["yfinance.cache"] = MagicMock()

import backend.database
# Ensure 'database' module resolves to 'backend.database' so patching works
sys.modules['database'] = backend.database

from backend.database import Database
from backend.agent_tools import ToolExecutor
from backend.worker import BackgroundWorker as Worker

# ... (fixture remains same) ...

def test_worker_check_alerts(test_db):
    """Test the worker job checking alerts."""
    # Patch Database class to return our test_db mock when Worker initializes
    # We patch backend.database.Database because we aliased 'database' to 'backend.database'
    with patch('backend.database.Database', return_value=test_db):
        worker = Worker()
    
    # Mock active alerts
    active_alerts = [{
        "id": 303,
        "symbol": "TSLA",
        "condition_type": "price",
        "condition_params": {"threshold": 100, "operator": "above"},
        "status": "active"
    }]
    test_db.get_all_active_alerts.return_value = active_alerts
    
    # Mock stock metrics (Price > 100, trigger condition)
    test_db.get_stock_metrics.return_value = {"price": 120}
    
    # Run the job
    worker._run_check_alerts(job_id=999, params={})
@pytest.fixture
def test_db():
    db = MagicMock(spec=Database)
    db.get_connection = MagicMock()
    db.return_connection = MagicMock()
    return db

def test_alert_creation_and_retrieval(test_db):
    """Test creating and retrieving alerts."""
    user_id = 1
    symbol = "AAPL"
    condition_type = "price"
    condition_params = {"threshold": 150, "operator": "above"}

    # Mock create_alert
    test_db.create_alert.return_value = 101
    
    # Mock get_alerts
    test_db.get_alerts.return_value = [{
        "id": 101,
        "symbol": symbol,
        "condition_type": condition_type,
        "condition_params": condition_params,
        "status": "active",
        "created_at": datetime.datetime.now()
    }]

    alert_id = test_db.create_alert(user_id, symbol, condition_type, condition_params)
    assert alert_id == 101

    alerts = test_db.get_alerts(user_id)
    assert len(alerts) == 1
    assert alerts[0]['symbol'] == "AAPL"
    assert alerts[0]['status'] == "active"

def test_agent_manage_alerts_tool(test_db):
    """Test the manage_alerts tool execution."""
    executor = ToolExecutor(test_db)
    
    # Mock create_alert
    test_db.create_alert.return_value = 202

    # Test Create
    result = executor._manage_alerts(
        action="create",
        ticker="GOOG",
        condition_type="price",
        threshold=2000,
        operator="below",
        user_id=1
    )
    
    assert "Successfully created alert" in result.get("message", "")
    test_db.create_alert.assert_called_with(1, "GOOG", "price", {"threshold": 2000, "operator": "below"})

    # Test List
    test_db.get_alerts.return_value = [{
        "id": 202,
        "symbol": "GOOG",
        "condition_type": "price",
        "condition_params": {"threshold": 2000, "operator": "below"},
        "status": "active",
        "created_at": datetime.datetime.now()
    }]
    
    result = executor._manage_alerts(action="list", user_id=1)
    assert "alerts" in result
    assert result["alerts"][0]["symbol"] == "GOOG"

    # Test Delete
    test_db.delete_alert.return_value = True
    result = executor._manage_alerts(action="delete", alert_id=202, user_id=1)
    assert "Successfully deleted alert" in result.get("message", "")


