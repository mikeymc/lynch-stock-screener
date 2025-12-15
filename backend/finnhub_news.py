# ABOUTME: Finnhub API client for fetching company news with pagination support
# ABOUTME: Handles rate limiting and fetches all available news for the last 2 years

import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class FinnhubNewsClient:
    """Client for fetching company news from Finnhub API"""
    
    BASE_URL = "https://finnhub.io/api/v1"
    RATE_LIMIT_DELAY = 1.0  # Delay between requests (60 calls/min = 1 call/sec)
    MAX_ARTICLES_PER_CALL = 150  # Finnhub returns max 150 articles per call
    LOOKBACK_YEARS = 2  # Fetch news from last 2 years
    
    def __init__(self, api_key: str):
        """
        Initialize Finnhub news client
        
        Args:
            api_key: Finnhub API key
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.last_request_time = 0
    
    def _rate_limit(self):
        """Enforce rate limiting to stay within 60 calls/min"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.RATE_LIMIT_DELAY:
            sleep_time = self.RATE_LIMIT_DELAY - time_since_last_request
            logger.info(f"[NewsFetcher] Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _fetch_news_page(
        self, 
        symbol: str, 
        from_date: str, 
        to_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch a single page of news articles from Finnhub
        
        Args:
            symbol: Stock ticker symbol
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            
        Returns:
            List of article dictionaries
        """
        self._rate_limit()
        
        url = f"{self.BASE_URL}/company-news"
        params = {
            'symbol': symbol.upper(),
            'from': from_date,
            'to': to_date,
            'token': self.api_key
        }
        
        try:
            logger.info(f"[NewsFetcher] Fetching news for {symbol} from {from_date} to {to_date}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            articles = response.json()
            logger.info(f"[NewsFetcher] Retrieved {len(articles)} articles for {symbol}")
            
            return articles if isinstance(articles, list) else []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[NewsFetcher] Error fetching news for {symbol}: {e}")
            return []
    
    def fetch_all_news(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Fetch all available news for a stock from the last 2 years.
        Handles pagination by making multiple requests if needed.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            List of all article dictionaries sorted by date descending
        """
        all_articles = []
        
        # Calculate date range
        to_date = datetime.now()
        from_date = to_date - timedelta(days=365 * self.LOOKBACK_YEARS)
        
        logger.info(f"[NewsFetcher] Starting news fetch for {symbol} from {from_date.date()} to {to_date.date()}")
        
        # Initial fetch
        to_date_str = to_date.strftime('%Y-%m-%d')
        from_date_str = from_date.strftime('%Y-%m-%d')
        
        articles = self._fetch_news_page(symbol, from_date_str, to_date_str)
        
        if not articles:
            logger.info(f"[NewsFetcher] No articles found for {symbol}")
            return []
        
        all_articles.extend(articles)
        
        # Check if we need to paginate
        # If we got exactly MAX_ARTICLES_PER_CALL, there might be more
        while len(articles) == self.MAX_ARTICLES_PER_CALL:
            # Find the oldest article's date from this batch
            oldest_article = min(articles, key=lambda x: x.get('datetime', 0))
            oldest_datetime = oldest_article.get('datetime', 0)
            
            if oldest_datetime == 0:
                logger.warning(f"[NewsFetcher] Article missing datetime field, stopping pagination")
                break
            
            # Convert Unix timestamp to datetime
            oldest_date = datetime.fromtimestamp(oldest_datetime)
            
            # Check if we've reached our lookback limit
            if oldest_date <= from_date:
                logger.info(f"[NewsFetcher] Reached {self.LOOKBACK_YEARS} year lookback limit for {symbol}")
                break
            
            # Fetch next page: from start date to one day before oldest article
            new_to_date = oldest_date - timedelta(days=1)
            new_to_date_str = new_to_date.strftime('%Y-%m-%d')
            
            logger.info(f"[NewsFetcher] Fetching next page for {symbol}: {from_date_str} to {new_to_date_str}")
            
            articles = self._fetch_news_page(symbol, from_date_str, new_to_date_str)
            
            if not articles:
                logger.info(f"[NewsFetcher] No more articles found for {symbol}")
                break
            
            all_articles.extend(articles)
        
        # Sort by datetime descending (most recent first)
        all_articles.sort(key=lambda x: x.get('datetime', 0), reverse=True)
        
        logger.info(f"[NewsFetcher] Total articles fetched for {symbol}: {len(all_articles)}")
        
        return all_articles
    
    def format_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format a raw Finnhub article into our standard format
        
        Args:
            article: Raw article dict from Finnhub API
            
        Returns:
            Formatted article dict
        """
        # Convert Unix timestamp to ISO format datetime
        datetime_unix = article.get('datetime', 0)
        published_date = datetime.fromtimestamp(datetime_unix) if datetime_unix else None
        
        return {
            'finnhub_id': article.get('id'),
            'headline': article.get('headline', ''),
            'summary': article.get('summary', ''),
            'source': article.get('source', ''),
            'url': article.get('url', ''),
            'image_url': article.get('image', ''),
            'category': article.get('category', ''),
            'datetime': datetime_unix,
            'published_date': published_date.isoformat() if published_date else None,
            'related': article.get('related', '')
        }
