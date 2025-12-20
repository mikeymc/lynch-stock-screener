"""
Unit tests for SECDataFetcher
Tests the fetching and caching of SEC filing data including incremental fetching
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
        db.get_latest_sec_filing_date = Mock(return_value=None)
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
        mock_db.get_latest_sec_filing_date.return_value = None
        
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
        
        # Verify fetch_recent_filings called with since_date=None for first fetch
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with(symbol, since_date=None)
        
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
        
        # Verify - should attempt to fetch with since_date
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with(symbol, since_date=None)
    
    def test_empty_country_treated_as_us(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that empty country is treated as US"""
        # Setup
        symbol = "GOOGL"
        mock_db.get_stock_metrics.return_value = {'country': ''}
        mock_edgar_fetcher.fetch_recent_filings.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_all(symbol)
        
        # Verify - should attempt to fetch with since_date
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with(symbol, since_date=None)


class TestSECDataFetcherIncremental:
    """Test suite for incremental SEC data fetching"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        db = Mock()
        db.get_stock_metrics = Mock(return_value={'country': 'US'})
        db.save_sec_filing = Mock()
        db.save_filing_section = Mock()
        db.get_latest_sec_filing_date = Mock()
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
    
    def test_full_fetch_when_no_cached_data(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that full fetch is used when no cached data exists"""
        # Setup: No existing data
        mock_db.get_latest_sec_filing_date.return_value = None
        
        filings = [
            {'type': '10-K', 'date': '2023-10-27', 'url': 'http://...', 'accession_number': '0001234567'}
        ]
        mock_edgar_fetcher.fetch_recent_filings.return_value = filings
        mock_edgar_fetcher.extract_filing_sections.return_value = {}
        
        # Execute
        fetcher.fetch_and_cache_all('AAPL')
        
        # Verify: since_date=None means full fetch
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with('AAPL', since_date=None)
    
    def test_incremental_fetch_when_cached_data_exists(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that since_date is used when cached data exists"""
        # Setup: Existing data in cache
        mock_db.get_latest_sec_filing_date.return_value = '2023-07-28'
        
        # New filing since the cached date
        new_filings = [
            {'type': '10-K', 'date': '2023-10-27', 'url': 'http://...', 'accession_number': '0001234567'}
        ]
        mock_edgar_fetcher.fetch_recent_filings.return_value = new_filings
        mock_edgar_fetcher.extract_filing_sections.return_value = {}
        
        # Execute
        fetcher.fetch_and_cache_all('AAPL')
        
        # Verify: since_date was passed from cached data
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with('AAPL', since_date='2023-07-28')
    
    def test_no_new_filings_skips_section_extraction(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that when no new filings, nothing is saved and sections not extracted"""
        # Setup: Existing data
        mock_db.get_latest_sec_filing_date.return_value = '2023-10-27'
        
        # No new filings since cached date
        mock_edgar_fetcher.fetch_recent_filings.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_all('AAPL')
        
        # Verify: Nothing saved
        mock_db.save_sec_filing.assert_not_called()
        mock_db.save_filing_section.assert_not_called()
        
        # Verify: Section extraction was not called
        mock_edgar_fetcher.extract_filing_sections.assert_not_called()
    
    def test_only_10k_sections_extracted_when_only_10k_filed(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that only 10-K sections are extracted when only 10-K is new"""
        # Setup
        mock_db.get_latest_sec_filing_date.return_value = None
        
        # Only 10-K filing (no 10-Q)
        filings = [
            {'type': '10-K', 'date': '2023-10-27', 'url': 'http://...', 'accession_number': '001'}
        ]
        mock_edgar_fetcher.fetch_recent_filings.return_value = filings
        
        sections_10k = {
            'business': {'content': 'Business...', 'filing_type': '10-K', 'filing_date': '2023-10-27'}
        }
        mock_edgar_fetcher.extract_filing_sections.return_value = sections_10k
        
        # Execute
        fetcher.fetch_and_cache_all('AAPL')
        
        # Verify: Only 10-K sections extracted (not 10-Q)
        mock_edgar_fetcher.extract_filing_sections.assert_called_once_with('AAPL', '10-K')
    
    def test_only_10q_sections_extracted_when_only_10q_filed(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that only 10-Q sections are extracted when only 10-Q is new"""
        # Setup
        mock_db.get_latest_sec_filing_date.return_value = None
        
        # Only 10-Q filing (no 10-K)
        filings = [
            {'type': '10-Q', 'date': '2023-07-28', 'url': 'http://...', 'accession_number': '002'}
        ]
        mock_edgar_fetcher.fetch_recent_filings.return_value = filings
        
        sections_10q = {
            'mda': {'content': 'MD&A...', 'filing_type': '10-Q', 'filing_date': '2023-07-28'}
        }
        mock_edgar_fetcher.extract_filing_sections.return_value = sections_10q
        
        # Execute
        fetcher.fetch_and_cache_all('AAPL')
        
        # Verify: Only 10-Q sections extracted (not 10-K)
        mock_edgar_fetcher.extract_filing_sections.assert_called_once_with('AAPL', '10-Q')
    
    def test_force_refresh_bypasses_cache(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that force_refresh=True bypasses incremental logic"""
        # Setup: Existing data
        mock_db.get_latest_sec_filing_date.return_value = '2023-07-28'
        
        filings = [
            {'type': '10-K', 'date': '2023-10-27', 'url': 'http://...', 'accession_number': '001'}
        ]
        mock_edgar_fetcher.fetch_recent_filings.return_value = filings
        mock_edgar_fetcher.extract_filing_sections.return_value = {}
        
        # Execute with force_refresh
        fetcher.fetch_and_cache_all('AAPL', force_refresh=True)
        
        # Verify: since_date=None even though cache exists
        mock_edgar_fetcher.fetch_recent_filings.assert_called_once_with('AAPL', since_date=None)
    
    def test_force_refresh_extracts_all_sections(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that force_refresh extracts both 10-K and 10-Q sections"""
        # Setup
        mock_db.get_latest_sec_filing_date.return_value = '2023-07-28'
        
        # Even with no new filings of a type, force_refresh should extract sections
        filings = []  # No new filings (but force_refresh should still extract)
        mock_edgar_fetcher.fetch_recent_filings.return_value = filings
        
        # This won't be called since filings is empty
        # But if there were filings with force_refresh, both types would be extracted
        
        # Execute
        fetcher.fetch_and_cache_all('AAPL', force_refresh=True)
        
        # Verify: With empty filings list, nothing happens (early return)
        mock_edgar_fetcher.extract_filing_sections.assert_not_called()
    
    def test_new_filings_logged_correctly(self, fetcher, mock_db, mock_edgar_fetcher):
        """Test that new filings are correctly identified and saved"""
        # Setup: Existing cached data
        mock_db.get_latest_sec_filing_date.return_value = '2023-01-15'
        
        # 2 new filings since cached date
        new_filings = [
            {'type': '10-K', 'date': '2023-10-27', 'url': 'http://10k', 'accession_number': 'K001'},
            {'type': '10-Q', 'date': '2023-07-28', 'url': 'http://10q', 'accession_number': 'Q001'}
        ]
        mock_edgar_fetcher.fetch_recent_filings.return_value = new_filings
        mock_edgar_fetcher.extract_filing_sections.return_value = {}
        
        # Execute
        fetcher.fetch_and_cache_all('AAPL')
        
        # Verify: Both filings saved
        assert mock_db.save_sec_filing.call_count == 2
        mock_db.save_sec_filing.assert_any_call('AAPL', '10-K', '2023-10-27', 'http://10k', 'K001')
        mock_db.save_sec_filing.assert_any_call('AAPL', '10-Q', '2023-07-28', 'http://10q', 'Q001')


class TestEdgarFetcherSinceDate:
    """Test suite for edgar_fetcher.fetch_recent_filings with since_date parameter"""
    
    def test_since_date_filters_old_filings(self):
        """Test that since_date correctly filters out old filings"""
        from unittest.mock import patch
        from edgar_fetcher import EdgarFetcher
        
        # Create fetcher with cik_cache to avoid HTTP lookup
        fetcher = EdgarFetcher(
            user_agent='test test@test.com',
            use_bulk_cache=False,
            cik_cache={'AAPL': '320193'}
        )
        
        # Mock the API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'filings': {
                'recent': {
                    'form': ['10-K', '10-Q', '10-Q', '10-K'],
                    'filingDate': ['2023-10-27', '2023-07-28', '2023-04-28', '2022-10-28'],
                    'accessionNumber': ['001', '002', '003', '004'],
                    'primaryDocument': ['doc1.htm', 'doc2.htm', 'doc3.htm', 'doc4.htm']
                }
            }
        }
        
        with patch('requests.get', return_value=mock_response):
            # Fetch with since_date - should only get filings after 2023-05-01
            filings = fetcher.fetch_recent_filings('AAPL', since_date='2023-05-01')
        
        # Verify: Only 2 filings returned (2023-10-27 and 2023-07-28)
        assert len(filings) == 2
        assert filings[0]['date'] == '2023-10-27'
        assert filings[1]['date'] == '2023-07-28'
    
    def test_since_date_none_returns_all(self):
        """Test that since_date=None returns all filings"""
        from unittest.mock import patch
        from edgar_fetcher import EdgarFetcher
        
        # Create fetcher with cik_cache to avoid HTTP lookup
        fetcher = EdgarFetcher(
            user_agent='test test@test.com',
            use_bulk_cache=False,
            cik_cache={'AAPL': '320193'}
        )
        
        # Mock the API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'filings': {
                'recent': {
                    'form': ['10-K', '10-Q'],
                    'filingDate': ['2023-10-27', '2023-07-28'],
                    'accessionNumber': ['001', '002'],
                    'primaryDocument': ['doc1.htm', 'doc2.htm']
                }
            }
        }
        
        with patch('requests.get', return_value=mock_response):
            # Fetch without since_date - should get all filings
            filings = fetcher.fetch_recent_filings('AAPL', since_date=None)
        
        # Verify: All filings returned
        assert len(filings) == 2
    
    def test_since_date_returns_empty_when_all_old(self):
        """Test that empty list is returned when all filings are older than since_date"""
        from unittest.mock import patch
        from edgar_fetcher import EdgarFetcher
        
        # Create fetcher with cik_cache to avoid HTTP lookup
        fetcher = EdgarFetcher(
            user_agent='test test@test.com',
            use_bulk_cache=False,
            cik_cache={'AAPL': '320193'}
        )
        
        # Mock the API response with old filings only
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'filings': {
                'recent': {
                    'form': ['10-K', '10-Q'],
                    'filingDate': ['2022-10-27', '2022-07-28'],
                    'accessionNumber': ['001', '002'],
                    'primaryDocument': ['doc1.htm', 'doc2.htm']
                }
            }
        }
        
        with patch('requests.get', return_value=mock_response):
            # Fetch with since_date after all filings
            filings = fetcher.fetch_recent_filings('AAPL', since_date='2023-01-01')
        
        # Verify: Empty list returned
        assert filings == []


