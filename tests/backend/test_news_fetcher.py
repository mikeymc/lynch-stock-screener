"""
Unit tests for NewsFetcher
Tests the fetching and caching of news articles
"""
import pytest
from unittest.mock import Mock
from news_fetcher import NewsFetcher


class TestNewsFetcher:
    """Test suite for NewsFetcher"""
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock database"""
        db = Mock()
        db.save_news_article = Mock()
        return db
    
    @pytest.fixture
    def mock_finnhub_client(self):
        """Create a mock Finnhub client"""
        client = Mock()
        client.fetch_all_news = Mock()
        client.format_article = Mock()
        return client
    
    @pytest.fixture
    def fetcher(self, mock_db, mock_finnhub_client):
        """Create a NewsFetcher instance"""
        return NewsFetcher(mock_db, mock_finnhub_client)
    
    def test_fetch_news_success(self, fetcher, mock_db, mock_finnhub_client):
        """Test successful news fetching"""
        # Setup
        symbol = "AAPL"
        raw_articles = [
            {'id': 1, 'headline': 'Apple announces...', 'datetime': 1234567890},
            {'id': 2, 'headline': 'Apple stock rises...', 'datetime': 1234567891}
        ]
        formatted_articles = [
            {'finnhub_id': 1, 'headline': 'Apple announces...', 'published_date': '2023-01-01'},
            {'finnhub_id': 2, 'headline': 'Apple stock rises...', 'published_date': '2023-01-01'}
        ]
        
        mock_finnhub_client.fetch_all_news.return_value = raw_articles
        mock_finnhub_client.format_article.side_effect = formatted_articles
        
        # Execute
        fetcher.fetch_and_cache_news(symbol)
        
        # Verify
        mock_finnhub_client.fetch_all_news.assert_called_once_with(symbol)
        assert mock_finnhub_client.format_article.call_count == 2
        assert mock_db.save_news_article.call_count == 2
        mock_db.save_news_article.assert_any_call(symbol, formatted_articles[0])
        mock_db.save_news_article.assert_any_call(symbol, formatted_articles[1])
    
    def test_fetch_news_no_articles(self, fetcher, mock_db, mock_finnhub_client):
        """Test handling when no news articles are found"""
        # Setup
        symbol = "NEWCO"
        mock_finnhub_client.fetch_all_news.return_value = None
        
        # Execute
        fetcher.fetch_and_cache_news(symbol)
        
        # Verify - should not save anything
        mock_db.save_news_article.assert_not_called()
    
    def test_fetch_news_empty_list(self, fetcher, mock_db, mock_finnhub_client):
        """Test handling when empty list is returned"""
        # Setup
        symbol = "AAPL"
        mock_finnhub_client.fetch_all_news.return_value = []
        
        # Execute
        fetcher.fetch_and_cache_news(symbol)
        
        # Verify - should not save anything
        mock_db.save_news_article.assert_not_called()
    
    def test_fetch_news_api_error(self, fetcher, mock_db, mock_finnhub_client):
        """Test handling of Finnhub API errors"""
        # Setup
        symbol = "AAPL"
        mock_finnhub_client.fetch_all_news.side_effect = Exception("Finnhub API Error")
        
        # Execute - should not raise exception
        fetcher.fetch_and_cache_news(symbol)
        
        # Verify - should not save anything
        mock_db.save_news_article.assert_not_called()
