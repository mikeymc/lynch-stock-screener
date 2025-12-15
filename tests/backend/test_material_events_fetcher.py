"""
Unit tests for MaterialEventsFetcher
Tests the fetching and caching of material events (8-K filings)
"""
import pytest
from unittest.mock import Mock
from material_events_fetcher import MaterialEventsFetcher


class TestMaterialEventsFetcher:
    """Test suite for MaterialEventsFetcher"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        db = Mock()
        db.save_material_event = Mock()
        return db
    
    @pytest.fixture
    def mock_sec_8k_client(self):
        """Create a mock SEC 8-K client"""
        client = Mock()
        client.fetch_recent_8ks = Mock()
        return client
    
    @pytest.fixture
    def fetcher(self, mock_db, mock_sec_8k_client):
        """Create a MaterialEventsFetcher instance"""
        return MaterialEventsFetcher(mock_db, mock_sec_8k_client)
    
    def test_fetch_events_success(self, fetcher, mock_db, mock_sec_8k_client):
        """Test successful material events fetching"""
        # Setup
        symbol = "AAPL"
        events = [
            {
                'event_type': '8k',
                'headline': 'Apple announces acquisition',
                'sec_accession_number': '0001234567',
                'filing_date': '2023-10-15'
            },
            {
                'event_type': '8k',
                'headline': 'Apple reports earnings',
                'sec_accession_number': '0001234568',
                'filing_date': '2023-11-01'
            }
        ]
        mock_sec_8k_client.fetch_recent_8ks.return_value = events
        
        # Execute
        fetcher.fetch_and_cache_events(symbol)
        
        # Verify
        mock_sec_8k_client.fetch_recent_8ks.assert_called_once_with(symbol)
        assert mock_db.save_material_event.call_count == 2
        mock_db.save_material_event.assert_any_call(symbol, events[0])
        mock_db.save_material_event.assert_any_call(symbol, events[1])
    
    def test_fetch_events_no_events(self, fetcher, mock_db, mock_sec_8k_client):
        """Test handling when no material events are found"""
        # Setup
        symbol = "NEWCO"
        mock_sec_8k_client.fetch_recent_8ks.return_value = None
        
        # Execute
        fetcher.fetch_and_cache_events(symbol)
        
        # Verify - should not save anything
        mock_db.save_material_event.assert_not_called()
    
    def test_fetch_events_empty_list(self, fetcher, mock_db, mock_sec_8k_client):
        """Test handling when empty list is returned"""
        # Setup
        symbol = "AAPL"
        mock_sec_8k_client.fetch_recent_8ks.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_events(symbol)
        
        # Verify - should not save anything
        mock_db.save_material_event.assert_not_called()
    
    def test_fetch_events_api_error(self, fetcher, mock_db, mock_sec_8k_client):
        """Test handling of SEC API errors"""
        # Setup
        symbol = "AAPL"
        mock_sec_8k_client.fetch_recent_8ks.side_effect = Exception("SEC API Error")
        
        # Execute - should not raise exception
        fetcher.fetch_and_cache_events(symbol)
        
        # Verify - should not save anything
        mock_db.save_material_event.assert_not_called()
