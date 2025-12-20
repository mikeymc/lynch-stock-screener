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
            logger.debug(f"[NewsFetcher] Rate limiting: sleeping for {sleep_time:.2f}s")
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
    
    def fetch_all_news(self, symbol: str, since_timestamp: int = None) -> List[Dict[str, Any]]:
        """
        Fetch news for a stock. Supports incremental fetching.
        
        Args:
            symbol: Stock ticker symbol
            since_timestamp: Optional Unix timestamp - only fetch articles newer than this.
                           Uses 1-day buffer to handle timezone edge cases.
            
        Returns:
            List of article dictionaries sorted by date descending
        """
        all_articles = []
        
        # Calculate date range
        to_date = datetime.now()
        
        if since_timestamp:
            # Incremental: start from 1 day before the most recent cached article
            # This ensures we don't miss any articles due to timezone differences
            from_date = datetime.fromtimestamp(since_timestamp) - timedelta(days=1)
            logger.info(f"[NewsFetcher] Incremental fetch for {symbol} since {from_date.date()}")
        else:
            # Full fetch: go back 2 years
            from_date = to_date - timedelta(days=365 * self.LOOKBACK_YEARS)
            logger.info(f"[NewsFetcher] Full fetch for {symbol} from {from_date.date()} to {to_date.date()}")
        
        # Fetch articles
        to_date_str = to_date.strftime('%Y-%m-%d')
        from_date_str = from_date.strftime('%Y-%m-%d')
        
        articles = self._fetch_news_page(symbol, from_date_str, to_date_str)
        
        if not articles:
            logger.debug(f"[NewsFetcher] No articles found for {symbol}")
            return []
        
        all_articles.extend(articles)
        
        # Sort by datetime descending (most recent first)
        all_articles.sort(key=lambda x: x.get('datetime', 0), reverse=True)
        
        logger.info(f"[NewsFetcher] Fetched {len(all_articles)} articles for {symbol}")
        
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
