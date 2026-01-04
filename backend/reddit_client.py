# ABOUTME: Reddit client for fetching stock-related posts and comments via JSON endpoints
# ABOUTME: Provides rate-limited access to Reddit's public JSON API for sentiment analysis

import requests
import time
import threading
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class RedditRateLimiter:
    """
    Thread-safe rate limiter for Reddit API requests.
    
    Reddit's public JSON endpoints can be accessed without auth, but they
    enforce strict rate limits. We stay well under to avoid 429/403 blocks.
    """
    
    def __init__(self, requests_per_minute: float = 20.0):
        """
        Initialize the rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute (default 20 to be safe)
        """
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self.lock = threading.Lock()
        self.last_request_time = 0.0
        self.request_count = 0
        
        logger.info(f"Reddit Rate Limiter initialized: {requests_per_minute} req/min (interval: {self.min_interval:.2f}s)")
    
    def acquire(self, caller: str = "unknown") -> float:
        """
        Block until it's safe to make a Reddit API request.
        
        Args:
            caller: Identifier for logging
            
        Returns:
            Time waited in seconds
        """
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            wait_time = 0.0
            
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                time.sleep(wait_time)
            
            self.last_request_time = time.time()
            self.request_count += 1
            
            if self.request_count % 10 == 0:
                logger.debug(f"[RedditRateLimiter] {self.request_count} requests made")
            
            return wait_time


# Global singleton
REDDIT_RATE_LIMITER = RedditRateLimiter(requests_per_minute=20.0)


class RedditClient:
    """
    Client for fetching Reddit posts and comments via public JSON endpoints.
    
    Uses direct .json URL suffix to access Reddit data without OAuth.
    Rate limited to avoid blocks.
    """
    
    BASE_URL = "https://www.reddit.com"
    
    # Subreddits most relevant for quality stock discussion (ordered by signal quality)
    DEFAULT_SUBREDDITS = ["SecurityAnalysis", "valueinvesting", "stocks", "investing"]
    
    def __init__(self, rate_limiter: RedditRateLimiter = None):
        """
        Initialize the Reddit client.
        
        Args:
            rate_limiter: Optional custom rate limiter (uses global singleton by default)
        """
        self.rate_limiter = rate_limiter or REDDIT_RATE_LIMITER
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
        })
    
    def _request(self, url: str, caller: str = "unknown") -> Optional[Dict]:
        """
        Make a rate-limited request to Reddit.
        
        Args:
            url: Full URL to request (should end in .json)
            caller: Identifier for logging
            
        Returns:
            JSON response as dict, or None on error
        """
        self.rate_limiter.acquire(caller)
        
        try:
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning(f"[RedditClient] Rate limited (429) for {caller}")
                time.sleep(60)  # Back off for a minute
                return None
            elif response.status_code == 403:
                logger.warning(f"[RedditClient] Access denied (403) for {caller}")
                return None
            else:
                logger.warning(f"[RedditClient] HTTP {response.status_code} for {caller}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"[RedditClient] Timeout for {caller}")
            return None
        except Exception as e:
            logger.error(f"[RedditClient] Error for {caller}: {e}")
            return None
    
    def search_posts(
        self,
        query: str,
        subreddit: str = None,
        sort: str = "relevance",
        time_filter: str = "month",
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Search for posts matching a query.
        
        Args:
            query: Search term (e.g., stock symbol)
            subreddit: Optional subreddit to restrict search to
            sort: Sort order: relevance, hot, top, new, comments
            time_filter: Time period: hour, day, week, month, year, all
            limit: Max results (up to 100)
            
        Returns:
            List of post dicts with normalized fields
        """
        if subreddit:
            url = f"{self.BASE_URL}/r/{subreddit}/search.json?q={query}&sort={sort}&t={time_filter}&restrict_sr=on&limit={limit}"
        else:
            url = f"{self.BASE_URL}/search.json?q={query}&sort={sort}&t={time_filter}&limit={limit}"
        
        data = self._request(url, f"search:{query}")
        if not data:
            return []
        
        posts = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            posts.append(self._normalize_post(post_data))
        
        return posts
    
    def get_top_posts(
        self,
        subreddit: str,
        time_filter: str = "week",
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Get top posts from a subreddit.
        
        Args:
            subreddit: Subreddit name
            time_filter: Time period: hour, day, week, month, year, all
            limit: Max results
            
        Returns:
            List of normalized post dicts
        """
        url = f"{self.BASE_URL}/r/{subreddit}/top.json?t={time_filter}&limit={limit}"
        
        data = self._request(url, f"top:{subreddit}")
        if not data:
            return []
        
        posts = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})
            posts.append(self._normalize_post(post_data))
        
        return posts
    
    def get_post_with_comments(
        self,
        subreddit: str,
        post_id: str,
        comment_sort: str = "top",
        comment_limit: int = 50
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single post with its comment tree.
        
        Args:
            subreddit: Subreddit name
            post_id: Reddit post ID (the alphanumeric string, not full name)
            comment_sort: Sort comments by: top, best, new, controversial
            comment_limit: Max top-level comments to retrieve
            
        Returns:
            Dict with post and comments, or None on error
        """
        url = f"{self.BASE_URL}/r/{subreddit}/comments/{post_id}.json?sort={comment_sort}&limit={comment_limit}"
        
        data = self._request(url, f"comments:{post_id}")
        if not data or len(data) < 2:
            return None
        
        # Reddit returns [post_listing, comment_listing]
        post_data = data[0]["data"]["children"][0]["data"]
        comment_listing = data[1]["data"]["children"]
        
        post = self._normalize_post(post_data)
        post["comments"] = [
            self._normalize_comment(c["data"]) 
            for c in comment_listing 
            if c.get("kind") == "t1"  # t1 = comment, t3 = post
        ]
        
        return post
    
    def get_subreddit_about(self, subreddit: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata about a subreddit.
        
        Args:
            subreddit: Subreddit name
            
        Returns:
            Dict with subreddit info (subscribers, description, etc.)
        """
        url = f"{self.BASE_URL}/r/{subreddit}/about.json"
        
        data = self._request(url, f"about:{subreddit}")
        if not data:
            return None
        
        about_data = data.get("data", {})
        return {
            "name": about_data.get("display_name"),
            "title": about_data.get("title"),
            "subscribers": about_data.get("subscribers"),
            "active_users": about_data.get("accounts_active"),
            "description": about_data.get("public_description"),
            "created_utc": about_data.get("created_utc"),
        }
    
    def _normalize_post(self, data: Dict) -> Dict[str, Any]:
        """Normalize raw Reddit post data to consistent format."""
        return {
            "id": data.get("id"),
            "subreddit": data.get("subreddit"),
            "title": data.get("title"),
            "author": data.get("author"),
            "score": data.get("score", 0),
            "upvote_ratio": data.get("upvote_ratio", 0),
            "num_comments": data.get("num_comments", 0),
            "url": f"https://www.reddit.com{data.get('permalink', '')}",
            "selftext": data.get("selftext", ""),
            "created_utc": data.get("created_utc"),
            "created_at": datetime.utcfromtimestamp(data.get("created_utc", 0)).isoformat() if data.get("created_utc") else None,
            "is_self": data.get("is_self", True),
            "link_flair_text": data.get("link_flair_text"),
        }
    
    def _normalize_comment(self, data: Dict, min_reply_score: int = 20) -> Dict[str, Any]:
        """Normalize raw Reddit comment data to consistent format, including replies."""
        # Handle "more" placeholders
        if data.get("id") == "_":
            return None
        
        # Extract nested replies if available
        replies = []
        if data.get("replies") and isinstance(data["replies"], dict):
            reply_children = data["replies"].get("data", {}).get("children", [])
            for r in reply_children[:3]:  # Limit to 3 replies per comment
                if r.get("kind") == "t1":
                    reply_data = r["data"]
                    if reply_data.get("score", 0) >= min_reply_score and reply_data.get("author") not in ["AutoModerator", "[deleted]"]:
                        replies.append({
                            "id": reply_data.get("id"),
                            "author": reply_data.get("author"),
                            "body": reply_data.get("body", ""),
                            "score": reply_data.get("score", 0),
                            "created_at": datetime.utcfromtimestamp(reply_data.get("created_utc", 0)).isoformat() if reply_data.get("created_utc") else None,
                        })
            
        return {
            "id": data.get("id"),
            "author": data.get("author"),
            "body": data.get("body", ""),
            "score": data.get("score", 0),
            "created_utc": data.get("created_utc"),
            "created_at": datetime.utcfromtimestamp(data.get("created_utc", 0)).isoformat() if data.get("created_utc") else None,
            "is_submitter": data.get("is_submitter", False),
            "parent_id": data.get("parent_id"),
            "replies": replies,
        }
    
    def find_stock_mentions(
        self,
        symbol: str,
        subreddits: List[str] = None,
        time_filter: str = "year",
        min_score: int = 50,
        min_comments: int = 20,
        min_body_length: int = 500,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Find high-quality analysis posts about a stock.
        
        Uses multiple search queries (DD, analysis, thesis) to find substantive content.
        Filters for high engagement and post length to ensure quality.
        
        Args:
            symbol: Stock ticker (e.g., "AAPL")
            subreddits: List of subreddits to search (default: DEFAULT_SUBREDDITS)
            time_filter: Time period to search (year for better quality)
            min_score: Minimum post score (50+ for quality)
            min_comments: Minimum comment count (20+ indicates debate)
            min_body_length: Minimum selftext length (500+ chars for substance)
            max_results: Maximum total results
            
        Returns:
            List of posts sorted by date (most recent first)
        """
        subreddits = subreddits or self.DEFAULT_SUBREDDITS
        all_posts = []
        
        # Multiple search queries to find substantive content
        search_queries = [
            f"{symbol} DD",           # Due Diligence posts
            f"{symbol} analysis",     # Analysis posts  
            f"{symbol} valuation",    # Valuation discussions
            f"{symbol} thesis",       # Investment thesis posts
            symbol,                   # Direct ticker mentions (fallback)
        ]
        
        for subreddit in subreddits:
            for query in search_queries:
                posts = self.search_posts(
                    query=query,
                    subreddit=subreddit,
                    sort="top",
                    time_filter=time_filter,
                    limit=15  # Smaller per-query, more queries
                )
                all_posts.extend(posts)
        
        # Quality filters
        filtered = []
        for p in all_posts:
            # Score threshold
            if p.get("score", 0) < min_score:
                continue
            # Comment count threshold (indicates discussion)
            if p.get("num_comments", 0) < min_comments:
                continue
            # Body length threshold (filters one-liners)
            body_len = len(p.get("selftext", "") or "")
            if body_len < min_body_length:
                continue
            filtered.append(p)
        
        # Sort by date descending (most recent first)
        filtered.sort(key=lambda p: p.get("created_utc", 0), reverse=True)
        
        # Deduplicate by ID
        seen = set()
        unique = []
        for p in filtered:
            if p["id"] not in seen:
                seen.add(p["id"])
                unique.append(p)
        
        return unique[:max_results]
    
    def get_top_conversation(
        self,
        subreddit: str,
        post_id: str,
        min_comment_score: int = 30,
        min_reply_score: int = 20
    ) -> Optional[Dict[str, Any]]:
        """
        Get ALL high-quality top-level comments and their replies for a post.
        
        Args:
            subreddit: Subreddit name
            post_id: Post ID
            min_comment_score: Minimum score for top-level comments to be included
            min_reply_score: Minimum score for replies to be included
            
        Returns:
            Dict with 'comments' list, each containing comment and replies
        """
        full_post = self.get_post_with_comments(subreddit, post_id, comment_limit=20)
        
        if not full_post or not full_post.get("comments"):
            return None
        
        # Filter to high-quality top-level comments
        quality_comments = [
            c for c in full_post["comments"] 
            if c and c.get("score", 0) >= min_comment_score 
            and c.get("author") not in ["AutoModerator", "[deleted]"]
        ]
        
        if not quality_comments:
            return None
        
        # Sort by score descending
        quality_comments.sort(key=lambda c: c.get("score", 0), reverse=True)
        
        # Limit to top 5 comments to avoid UI overload
        quality_comments = quality_comments[:5]
        
        # For each quality comment, we could fetch replies, but that's expensive
        # For now, just return the comments without deep replies (replies are already excluded from base fetch)
        # The comment body is the main value anyway
        
        return {
            "comments": quality_comments,
            "count": len(quality_comments)
        }
    
    def find_stock_mentions_with_conversations(
        self,
        symbol: str,
        subreddits: List[str] = None,
        time_filter: str = "year",
        max_results: int = 20,
        min_comment_score: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Find quality analysis posts and enrich ALL posts with conversations.
        
        Args:
            symbol: Stock ticker
            subreddits: Subreddits to search
            time_filter: Time period (year default for quality)
            max_results: Max posts to return
            min_comment_score: Minimum score for comments to include
            
        Returns:
            List of posts, each with 'conversation' field populated
        """
        posts = self.find_stock_mentions(
            symbol=symbol,
            subreddits=subreddits,
            time_filter=time_filter,
            max_results=max_results
            # uses improved internal defaults: min_score=50, min_comments=20, min_body_length=500
        )
        
        # Fetch conversations for ALL posts
        for post in posts:
            try:
                conversation = self.get_top_conversation(
                    subreddit=post["subreddit"],
                    post_id=post["id"],
                    min_comment_score=min_comment_score
                )
                post["conversation"] = conversation
            except Exception as e:
                logger.warning(f"Failed to fetch conversation for {post['id']}: {e}")
                post["conversation"] = None
        
        return posts


def calculate_simple_sentiment(text: str) -> float:
    """
    Calculate a simple sentiment score for text.
    
    Uses a basic keyword-based approach. For production, consider
    using VADER or TextBlob.
    
    Args:
        text: Text to analyze
        
    Returns:
        Score from -1.0 (bearish) to 1.0 (bullish)
    """
    if not text:
        return 0.0
    
    text_lower = text.lower()
    
    # Simple keyword lists
    bullish_words = [
        "buy", "bullish", "moon", "rocket", "undervalued", "growth",
        "strong", "profit", "gains", "up", "long", "calls", "breakout",
        "beat", "exceeded", "outperform", "upgrade", "opportunity"
    ]
    
    bearish_words = [
        "sell", "bearish", "crash", "dump", "overvalued", "declining",
        "weak", "loss", "losses", "down", "short", "puts", "breakdown",
        "miss", "missed", "underperform", "downgrade", "risk", "avoid"
    ]
    
    bullish_count = sum(1 for word in bullish_words if word in text_lower)
    bearish_count = sum(1 for word in bearish_words if word in text_lower)
    
    total = bullish_count + bearish_count
    if total == 0:
        return 0.0
    
    # Score between -1 and 1
    score = (bullish_count - bearish_count) / total
    return round(score, 2)


# CLI for testing
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    print(f"\n=== Finding Reddit mentions for {symbol} ===\n")
    
    client = RedditClient()
    posts = client.find_stock_mentions(symbol, time_filter="month", min_score=20)
    
    print(f"Found {len(posts)} high-quality posts:\n")
    
    for i, post in enumerate(posts[:5], 1):
        sentiment = calculate_simple_sentiment(post["title"] + " " + post["selftext"])
        sentiment_label = "🟢 Bullish" if sentiment > 0.2 else ("🔴 Bearish" if sentiment < -0.2 else "⚪ Neutral")
        
        print(f"[{i}] {post['title'][:60]}...")
        print(f"    Score: {post['score']} | Comments: {post['num_comments']} | {sentiment_label}")
        print(f"    r/{post['subreddit']} | {post['created_at'][:10]}")
        print(f"    {post['url']}")
        print()
    
    # Deep dive into top post
    if posts:
        top_post = posts[0]
        print(f"\n=== Deep dive: Top Post Comments ===\n")
        
        full_post = client.get_post_with_comments(top_post["subreddit"], top_post["id"])
        if full_post and full_post.get("comments"):
            for j, comment in enumerate(full_post["comments"][:3], 1):
                if comment:
                    print(f"  [{j}] Score: {comment['score']} | {comment['author']}")
                    print(f"      {comment['body'][:100]}...")
                    print()
