# ABOUTME: Fetches and caches news articles from Finnhub
# ABOUTME: Handles news article formatting and database storage with incremental updates

import logging
from typing import Optional
from database import Database
from finnhub_news import FinnhubNewsClient

logger = logging.getLogger(__name__)


class NewsFetcher:
    """Fetches and caches news articles for stocks"""
    
    def __init__(self, db: Database, finnhub_client: FinnhubNewsClient):
        self.db = db
        self.finnhub_client = finnhub_client
    
    def fetch_and_cache_news(self, symbol: str):
        """
        Fetch and cache news articles for a symbol.
        
        Uses incremental fetching: only retrieves articles newer than the most
        recent cached one (with 1-day buffer for timezone safety).
        Database ON CONFLICT handles any duplicates.
        
        Args:
            symbol: Stock ticker symbol
        """
        try:
            # Check for existing cached news to determine fetch strategy
            since_timestamp = self.db.get_latest_news_timestamp(symbol)
            
            if since_timestamp:
                logger.debug(f"[NewsFetcher][{symbol}] Incremental update from timestamp {since_timestamp}")
            else:
                logger.debug(f"[NewsFetcher][{symbol}] Full history fetch (no existing data)")
            
            # Fetch articles (incremental if we have existing data)
            articles = self.finnhub_client.fetch_all_news(symbol, since_timestamp=since_timestamp)
            
            if not articles:
                if since_timestamp:
                    logger.debug(f"[NewsFetcher][{symbol}] Already up to date")
                else:
                    logger.debug(f"[NewsFetcher][{symbol}] No news articles available")
                return
            
            # Format and save articles
            for article in articles:
                formatted = self.finnhub_client.format_article(article)
                self.db.save_news_article(symbol, formatted)
            
            logger.info(f"[NewsFetcher][{symbol}] Cached {len(articles)} news articles")
        
        except Exception as e:
            logger.error(f"[NewsFetcher][{symbol}] Error caching news: {e}")
            # Don't raise - news is optional

