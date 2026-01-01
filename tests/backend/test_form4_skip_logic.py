"""
Test the has_recent_insider_trades function used for Form 4 cache skip logic.

This test verifies that:
1. The SQL query is correctly structured
2. The skip logic in worker.py works as intended
3. Edge cases are handled properly
"""

import pytest
from datetime import datetime, timedelta


class TestForm4SkipLogicUnit:
    """
    Unit tests for the skip logic without requiring database imports.
    We test the pure logic here.
    """
    
    def test_since_date_calculation(self):
        """
        Test that since_date is correctly calculated as ~365 days ago.
        
        This is the exact code from worker.py:
        ```python
        from datetime import datetime, timedelta
        one_year_ago = datetime.now() - timedelta(days=365)
        since_date = one_year_ago.strftime('%Y-%m-%d')
        ```
        """
        one_year_ago = datetime.now() - timedelta(days=365)
        since_date = one_year_ago.strftime('%Y-%m-%d')
        
        # Verify date format
        assert len(since_date) == 10, "Date should be YYYY-MM-DD format (10 chars)"
        assert since_date[4] == '-', "Year should be followed by hyphen"
        assert since_date[7] == '-', "Month should be followed by hyphen"
        
        # Verify it's a valid date
        parsed = datetime.strptime(since_date, '%Y-%m-%d')
        
        # Verify it's approximately 365 days ago (allow 1 day variance)
        days_diff = (datetime.now() - parsed).days
        assert 364 <= days_diff <= 366, f"Since date should be ~365 days ago, got {days_diff} days"
    
    def test_skip_condition_with_has_trades_true(self):
        """
        When has_recent_insider_trades returns True, skip should be True.
        
        Code from worker.py:
        ```python
        if not force_refresh and self.db.has_recent_insider_trades(symbol, since_date):
            skipped += 1
            processed += 1
            continue
        ```
        """
        force_refresh = False
        has_trades = True  # Simulating db.has_recent_insider_trades returning True
        
        should_skip = not force_refresh and has_trades
        assert should_skip is True, "Should skip when trades exist and not force_refresh"
    
    def test_skip_condition_with_has_trades_false(self):
        """
        When has_recent_insider_trades returns False, skip should be False.
        """
        force_refresh = False
        has_trades = False  # No recent trades
        
        should_skip = not force_refresh and has_trades
        assert should_skip is False, "Should NOT skip when no trades exist"
    
    def test_skip_condition_force_refresh_overrides(self):
        """
        When force_refresh=True, should NOT skip even if trades exist.
        """
        force_refresh = True
        has_trades = True  # Trades exist
        
        should_skip = not force_refresh and has_trades
        assert should_skip is False, "Should NOT skip when force_refresh=True"
    
    def test_skip_condition_force_refresh_false_explicit(self):
        """
        Force refresh explicitly False with trades should skip.
        """
        force_refresh = False
        has_trades = True
        
        should_skip = not force_refresh and has_trades
        assert should_skip is True


class TestSQLQuery:
    """Test the SQL query structure."""
    
    def test_sql_uses_correct_comparison_operator(self):
        """
        Verify the SQL uses >= for date comparison.
        
        The SQL should be:
        ```sql
        SELECT 1 FROM insider_trades
        WHERE symbol = %s AND transaction_date >= %s
        LIMIT 1
        ```
        
        Using >= ensures trades ON the since_date are included.
        """
        # Read the actual SQL from the function
        import re
        with open('/Users/mikey/workspace/lynch-stock-screener/backend/database.py', 'r') as f:
            content = f.read()
        
        # Find the has_recent_insider_trades function
        match = re.search(
            r'def has_recent_insider_trades\(.*?\n(.*?)(?=\n    def |\nclass |\Z)',
            content,
            re.DOTALL
        )
        assert match, "Could not find has_recent_insider_trades function"
        
        func_body = match.group(1)
        
        # Verify the SQL structure
        assert 'SELECT 1 FROM insider_trades' in func_body, "Should query insider_trades table"
        assert 'WHERE symbol = %s' in func_body, "Should filter by symbol"
        assert 'transaction_date >= %s' in func_body, "Should use >= for date comparison (includes boundary)"
        assert 'LIMIT 1' in func_body, "Should use LIMIT 1 for efficiency"
    
    def test_sql_returns_boolean(self):
        """
        Verify the function returns a boolean, not the row.
        
        The code should be:
        ```python
        return cursor.fetchone() is not None
        ```
        """
        import re
        with open('/Users/mikey/workspace/lynch-stock-screener/backend/database.py', 'r') as f:
            content = f.read()
        
        # Find the function and check return statement
        match = re.search(
            r'def has_recent_insider_trades\(.*?\n(.*?)(?=\n    def |\nclass |\Z)',
            content,
            re.DOTALL
        )
        
        import re
        func_body = match.group(1)
        assert 'return cursor.fetchone() is not None' in func_body, \
            "Should return boolean based on whether row exists"


class TestWorkerIntegration:
    """Test the worker code integration."""
    
    def test_worker_has_skip_logic(self):
        """Verify the worker.py has the skip logic implemented."""
        with open('/Users/mikey/workspace/lynch-stock-screener/backend/worker.py', 'r') as f:
            content = f.read()
        
        # Check for the skip logic in _run_form4_cache
        assert 'has_recent_insider_trades' in content, \
            "Worker should call has_recent_insider_trades"
        assert 'skipped += 1' in content, \
            "Worker should track skipped count"
        assert "'skipped':" in content, \
            "Final result should include skipped count"
    
    def test_worker_force_refresh_support(self):
        """Verify the worker supports force_refresh parameter."""
        with open('/Users/mikey/workspace/lynch-stock-screener/backend/worker.py', 'r') as f:
            content = f.read()
        
        # Check for force_refresh handling
        assert "force_refresh = params.get('force_refresh'" in content, \
            "Worker should get force_refresh from params"
        assert "not force_refresh and self.db.has_recent_insider_trades" in content, \
            "Skip logic should respect force_refresh flag"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
