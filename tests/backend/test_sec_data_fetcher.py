"""
Unit tests for SECDataFetcher
Tests the fetching and caching of SEC filing data
"""
import pytest
from unittest.mock import Mock, MagicMock
from sec_data_fetcher import SECDataFetcher


class TestSECDataFetcher:
    """Test suite for SECDataFetcher"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        db = Mock()
        db.get_stock_metrics = Mock()
        db.save_sec_filing = Mock()
        db.save_filing_section = Mock()
        # Mock cache validity methods - return False so fetching proceeds
        db.is_filings_cache_valid = Mock(return_value=False)
        db.is_sections_cache_valid = Mock(return_value=False)
        return db
    
    @pytest.fixture
    def mock_edgar_fetcher(self):
        """Create a mock EDGAR fetcher"""
        fetcher = Mock()
        fetcher.fetch_recent_filings = Mock()
        fetcher.extract_filing_sections = Mock()
        return fetcher
    
    @pytest.fixture
    def fetcher(self, mock_db, mock_edgar_fetcher):
        """Create a SECDataFetcher instance"""
        return SECDataFetcher(mock_db, mock_edgar_fetcher)
    
    def test_fetch_us_stock_success(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test successful SEC data fetching for US stock"""
        # Setup
        symbol = "AAPL"
        mock_db.get_stock_metrics.return_value = {'country': 'US'}
        
        filings = [
            {'type': '10-K', 'date': '2023-10-27', 'url': 'http://...', 'accession_number': '0001234567'},
            {'type': '10-Q', 'date': '2023-07-28', 'url': 'http://...', 'accession_number': '0001234568'}
        ]
        mock_edgar_fetcher.fetch_recent_filings.return_value = filings
        
        sections_10k = {
            'business': {'content': 'Business description...', 'filing_type': '10-K', 'filing_date': '2023-10-27'},
            'risk_factors': {'content': 'Risk factors...', 'filing_type': '10-K', 'filing_date': '2023-10-27'}
        }
        sections_10q = {
            'mda': {'content': 'MD&A...', 'filing_type': '10-Q', 'filing_date': '2023-07-28'}
        }
        mock_edgar_fetcher.extract_filing_sections.side_effect = [sections_10k, sections_10q]
        
        # Execute
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify filings saved
        assert mock_db.save_sec_filing.call_count == 2
        mock_db.save_sec_filing.assert_any_call(symbol, '10-K', '2023-10-27', 'http://...', '0001234567')
        
        # Verify sections saved
        assert mock_db.save_filing_section.call_count == 3
        mock_db.save_filing_section.assert_any_call(
            symbol, 'business', 'Business description...', '10-K', '2023-10-27'
        )
    
    def test_skip_non_us_stock(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that non-US stocks are skipped"""
        # Setup
        symbol = "TSM"
        mock_db.get_stock_metrics.return_value = {'country': 'Taiwan'}
        
        # Execute
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify - should not fetch anything
        mock_edgar_fetcher.fetch_recent_filings.assert_not_called()
        mock_edgar_fetcher.extract_filing_sections.assert_not_called()
        mock_db.save_sec_filing.assert_not_called()
        mock_db.save_filing_section.assert_not_called()
    
    def test_handle_no_filings(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test handling when no filings are found"""
        # Setup
        symbol = "NEWCO"
        mock_db.get_stock_metrics.return_value = {'country': 'US'}
        mock_edgar_fetcher.fetch_recent_filings.return_value = None
        
        # Execute - should not raise exception
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify
        mock_db.save_sec_filing.assert_not_called()
    
    def test_handle_no_sections(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test handling when no sections are extracted"""
        # Setup
        symbol = "AAPL"
        mock_db.get_stock_metrics.return_value = {'country': 'US'}
        mock_edgar_fetcher.fetch_recent_filings.return_value = []
        mock_edgar_fetcher.extract_filing_sections.return_value = None
        
        # Execute
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify - should not save sections
        mock_db.save_filing_section.assert_not_called()
    
    def test_handle_edgar_error(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test handling of EDGAR API errors"""
        # Setup
        symbol = "AAPL"
        mock_db.get_stock_metrics.return_value = {'country': 'US'}
        mock_edgar_fetcher.fetch_recent_filings.side_effect = Exception("EDGAR API Error")
        
        # Execute - should not raise exception (errors are logged but not propagated)
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify - should not save anything
        mock_db.save_sec_filing.assert_not_called()
    
    def test_usa_country_variant(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that 'USA' country variant is recognized"""
        # Setup
        symbol = "MSFT"
        mock_db.get_stock_metrics.return_value = {'country': 'USA'}
        mock_edgar_fetcher.fetch_recent_filings.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify - should attempt to fetch
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with(symbol)
    
    def test_empty_country_treated_as_us(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that empty country is treated as US"""
        # Setup
        symbol = "GOOGL"
        mock_db.get_stock_metrics.return_value = {'country': ''}
        mock_edgar_fetcher.fetch_recent_filings.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify - should attempt to fetch
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with(symbol)
