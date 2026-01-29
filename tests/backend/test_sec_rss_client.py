# ABOUTME: Tests for SEC RSS client
# ABOUTME: Validates RSS feed parsing and CIK-to-ticker mapping

import pytest
from unittest.mock import Mock, patch, MagicMock
from sec_rss_client import SECRSSClient


class TestSECRSSClient:
    """Tests for SECRSSClient"""

    @pytest.fixture
    def client(self):
        """Create test SEC RSS client"""
        return SECRSSClient("Test User Agent test@example.com")

    @pytest.fixture
    def sample_rss_response(self):
        """Sample RSS feed XML response"""
        return """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings</title>
<entry>
<title>8-K - APPLE INC (0000320193) (Filer)</title>
<updated>2024-01-28T17:30:59-05:00</updated>
</entry>
<entry>
<title>8-K - MICROSOFT CORP (0000789019) (Filer)</title>
<updated>2024-01-28T17:29:54-05:00</updated>
</entry>
<entry>
<title>8-K - ALPHABET INC (0001652044) (Filer)</title>
<updated>2024-01-28T17:28:57-05:00</updated>
</entry>
</feed>"""

    @pytest.fixture
    def sample_cik_mapping(self):
        """Sample CIK-to-ticker mapping"""
        return {
            "0": {
                "cik_str": 320193,
                "ticker": "AAPL",
                "title": "Apple Inc."
            },
            "1": {
                "cik_str": 789019,
                "ticker": "MSFT",
                "title": "Microsoft Corp"
            },
            "2": {
                "cik_str": 1652044,
                "ticker": "GOOGL",
                "title": "Alphabet Inc."
            }
        }

    def test_initialization(self, client):
        """Test client initializes correctly"""
        assert client.user_agent == "Test User Agent test@example.com"
        assert client.headers == {'User-Agent': "Test User Agent test@example.com"}
        assert client._cik_to_ticker_cache is None

    @patch('sec_rss_client.requests.get')
    def test_get_tickers_with_new_filings_success(self, mock_get, client, sample_rss_response, sample_cik_mapping):
        """Test successfully fetching tickers with new filings"""
        # Mock RSS feed response
        rss_mock = Mock()
        rss_mock.content = sample_rss_response.encode('utf-8')
        rss_mock.raise_for_status = Mock()

        # Mock CIK mapping response
        mapping_mock = Mock()
        mapping_mock.json.return_value = sample_cik_mapping
        mapping_mock.raise_for_status = Mock()

        # Return RSS feed first, then CIK mapping
        mock_get.side_effect = [rss_mock, mapping_mock]

        # Execute
        known_tickers = {'AAPL', 'MSFT', 'GOOGL', 'TSLA'}
        result = client.get_tickers_with_new_filings('8-K', known_tickers=known_tickers)

        # Verify
        assert result == {'AAPL', 'MSFT', 'GOOGL'}
        assert len(result) == 3
        assert 'TSLA' not in result  # No filing in RSS

    @patch('sec_rss_client.requests.get')
    def test_get_tickers_filters_to_known_tickers(self, mock_get, client, sample_rss_response, sample_cik_mapping):
        """Test that results are filtered to known tickers"""
        # Mock responses
        rss_mock = Mock()
        rss_mock.content = sample_rss_response.encode('utf-8')
        rss_mock.raise_for_status = Mock()

        mapping_mock = Mock()
        mapping_mock.json.return_value = sample_cik_mapping
        mapping_mock.raise_for_status = Mock()

        mock_get.side_effect = [rss_mock, mapping_mock]

        # Only provide subset of known tickers
        known_tickers = {'AAPL', 'TSLA'}  # MSFT and GOOGL not in known_tickers
        result = client.get_tickers_with_new_filings('8-K', known_tickers=known_tickers)

        # Should only return AAPL (in both RSS and known_tickers)
        assert result == {'AAPL'}
        assert 'MSFT' not in result  # Has filing but not in known_tickers
        assert 'GOOGL' not in result  # Has filing but not in known_tickers

    @patch('sec_rss_client.requests.get')
    def test_get_tickers_without_filter(self, mock_get, client, sample_rss_response, sample_cik_mapping):
        """Test fetching tickers without known_tickers filter"""
        # Mock responses
        rss_mock = Mock()
        rss_mock.content = sample_rss_response.encode('utf-8')
        rss_mock.raise_for_status = Mock()

        mapping_mock = Mock()
        mapping_mock.json.return_value = sample_cik_mapping
        mapping_mock.raise_for_status = Mock()

        mock_get.side_effect = [rss_mock, mapping_mock]

        # No known_tickers filter
        result = client.get_tickers_with_new_filings('8-K', known_tickers=None)

        # Should return all tickers found in RSS
        assert result == {'AAPL', 'MSFT', 'GOOGL'}

    def test_form_type_mapping(self, client):
        """Test that form types are correctly mapped"""
        assert SECRSSClient.FORM_TYPE_MAPPING['8-K'] == '8-K'
        assert SECRSSClient.FORM_TYPE_MAPPING['10-K'] == '10-K'
        assert SECRSSClient.FORM_TYPE_MAPPING['10-Q'] == '10-Q'
        assert SECRSSClient.FORM_TYPE_MAPPING['FORM4'] == '4'

    @patch('sec_rss_client.requests.get')
    def test_unknown_form_type(self, mock_get, client):
        """Test handling of unknown form type"""
        result = client.get_tickers_with_new_filings('UNKNOWN-FORM')
        assert result == set()
        mock_get.assert_not_called()

    @patch('sec_rss_client.requests.get')
    def test_rss_fetch_error(self, mock_get, client):
        """Test handling of RSS fetch errors"""
        mock_get.side_effect = Exception("Network error")

        result = client.get_tickers_with_new_filings('8-K')
        assert result == set()

    @patch('sec_rss_client.requests.get')
    def test_cik_mapping_caches(self, mock_get, client, sample_rss_response, sample_cik_mapping):
        """Test that CIK mapping is cached after first load"""
        # Mock responses
        rss_mock = Mock()
        rss_mock.content = sample_rss_response.encode('utf-8')
        rss_mock.raise_for_status = Mock()

        mapping_mock = Mock()
        mapping_mock.json.return_value = sample_cik_mapping
        mapping_mock.raise_for_status = Mock()

        # First call: RSS + mapping
        mock_get.side_effect = [rss_mock, mapping_mock]
        client.get_tickers_with_new_filings('8-K')

        # Second call: Only RSS (mapping should be cached)
        rss_mock2 = Mock()
        rss_mock2.content = sample_rss_response.encode('utf-8')
        rss_mock2.raise_for_status = Mock()
        mock_get.side_effect = [rss_mock2]

        client.get_tickers_with_new_filings('8-K')

        # Verify mapping was only fetched once
        assert mock_get.call_count == 3  # RSS + mapping + RSS (not mapping again)

    @pytest.fixture
    def sample_rss_with_ids(self):
        """Sample RSS response with accession numbers in ID tags"""
        return """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings</title>
<entry>
<title>8-K - APPLE INC (0000320193) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0001234567-26-001111</id>
</entry>
<entry>
<title>8-K - MICROSOFT CORP (0000789019) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0001234567-26-002222</id>
</entry>
<entry>
<title>8-K - ALPHABET INC (0001652044) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0001234567-26-003333</id>
</entry>
</feed>"""

    @patch('sec_rss_client.requests.get')
    def test_paginated_single_page(self, mock_get, client, sample_rss_with_ids, sample_cik_mapping):
        """Test pagination with single page (all new filings)"""
        # Page 1 RSS response
        rss_mock = Mock()
        rss_mock.content = sample_rss_with_ids.encode('utf-8')
        rss_mock.raise_for_status = Mock()

        # Page 2 - empty (end of feed)
        empty_rss = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""
        rss_mock2 = Mock()
        rss_mock2.content = empty_rss.encode('utf-8')
        rss_mock2.raise_for_status = Mock()

        # Mock CIK mapping
        mapping_mock = Mock()
        mapping_mock.json.return_value = sample_cik_mapping
        mapping_mock.raise_for_status = Mock()

        # Mock database (no filings exist)
        mock_db = Mock()
        mock_db.filing_exists.return_value = False

        mock_get.side_effect = [rss_mock, rss_mock2, mapping_mock]

        # Execute
        known_tickers = {'AAPL', 'MSFT', 'GOOGL'}
        result = client.get_tickers_with_new_filings_paginated('8-K', known_tickers=known_tickers, db=mock_db)

        # Verify
        assert result == {'AAPL', 'MSFT', 'GOOGL'}
        assert mock_db.filing_exists.call_count == 3  # Checked all 3 filings

    @patch('sec_rss_client.requests.get')
    def test_paginated_stop_on_known_filing(self, mock_get, client, sample_cik_mapping):
        """Test pagination stops when hitting a known filing"""
        # Page 1: 2 new filings
        page1_rss = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>8-K - APPLE INC (0000320193) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0001234567-26-001111</id>
</entry>
<entry>
<title>8-K - MICROSOFT CORP (0000789019) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0001234567-26-002222</id>
</entry>
<entry>
<title>8-K - ALPHABET INC (0001652044) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0001234567-26-003333</id>
</entry>
</feed>"""

        # Mock RSS response
        rss_mock = Mock()
        rss_mock.content = page1_rss.encode('utf-8')
        rss_mock.raise_for_status = Mock()

        # Mock CIK mapping
        mapping_mock = Mock()
        mapping_mock.json.return_value = sample_cik_mapping
        mapping_mock.raise_for_status = Mock()

        # Mock database - third filing exists
        mock_db = Mock()
        def filing_exists_side_effect(acc_num, form_type, ticker=None):
            return acc_num == '0001234567-26-003333'  # Third filing exists
        mock_db.filing_exists.side_effect = filing_exists_side_effect

        mock_get.side_effect = [rss_mock, mapping_mock]

        # Execute
        known_tickers = {'AAPL', 'MSFT', 'GOOGL'}
        result = client.get_tickers_with_new_filings_paginated('8-K', known_tickers=known_tickers, db=mock_db)

        # Verify - should only return first 2 tickers (stopped on 3rd)
        assert result == {'AAPL', 'MSFT'}
        assert 'GOOGL' not in result
        assert mock_db.filing_exists.call_count == 3  # Checked until hitting known

    @patch('sec_rss_client.requests.get')
    def test_paginated_multiple_pages(self, mock_get, client, sample_cik_mapping):
        """Test pagination across multiple pages"""
        # Page 1
        page1_rss = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>8-K - APPLE INC (0000320193) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0001111111-26-000001</id>
</entry>
</feed>"""

        # Page 2
        page2_rss = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>8-K - MICROSOFT CORP (0000789019) (Filer)</title>
<id>urn:tag:sec.gov,2008:accession-number=0002222222-26-000002</id>
</entry>
</feed>"""

        # Page 3 - empty (end of feed)
        page3_rss = """<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""

        # Mock responses
        rss_mock1 = Mock()
        rss_mock1.content = page1_rss.encode('utf-8')
        rss_mock1.raise_for_status = Mock()

        rss_mock2 = Mock()
        rss_mock2.content = page2_rss.encode('utf-8')
        rss_mock2.raise_for_status = Mock()

        rss_mock3 = Mock()
        rss_mock3.content = page3_rss.encode('utf-8')
        rss_mock3.raise_for_status = Mock()

        mapping_mock = Mock()
        mapping_mock.json.return_value = sample_cik_mapping
        mapping_mock.raise_for_status = Mock()

        # Mock database (no filings exist)
        mock_db = Mock()
        mock_db.filing_exists.return_value = False

        mock_get.side_effect = [rss_mock1, rss_mock2, rss_mock3, mapping_mock]

        # Execute
        known_tickers = {'AAPL', 'MSFT'}
        result = client.get_tickers_with_new_filings_paginated('8-K', known_tickers=known_tickers, db=mock_db)

        # Verify - should get both tickers from 2 pages
        assert result == {'AAPL', 'MSFT'}
        assert mock_db.filing_exists.call_count == 2

    @patch('sec_rss_client.requests.get')
    def test_paginated_unknown_form_type(self, mock_get, client):
        """Test pagination with unknown form type"""
        mock_db = Mock()
        result = client.get_tickers_with_new_filings_paginated('UNKNOWN-FORM', known_tickers=set(), db=mock_db)
        assert result == set()
        mock_get.assert_not_called()

    @patch('sec_rss_client.requests.get')
    def test_paginated_error_handling(self, mock_get, client):
        """Test pagination handles errors gracefully"""
        mock_get.side_effect = Exception("Network error")
        mock_db = Mock()

        result = client.get_tickers_with_new_filings_paginated('8-K', known_tickers=set(), db=mock_db)
        assert result == set()
