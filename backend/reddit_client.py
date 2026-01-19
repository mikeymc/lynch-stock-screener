
import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class RedditClient:
    """
    Client for fetching Reddit sentiment using Google Search Grounding with Gemini.
    
    This replaces the legacy direct Reddit API client to provide more robust
    "word on the street" sentiment analysis without rate limits or API flakiness.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        import os
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        self.model_name = "gemini-2.5-flash"
        self._client = None
        
    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client
        
    def _extract_id_from_url(self, url: str) -> str:
        """Extract Reddit post ID from URL."""
        if not url:
            return f"unknown_{datetime.now().timestamp()}"
        
        # Standard pattern: comments/ID/title
        match = re.search(r'comments/([a-z0-9]+)/', url)
        if match:
            return match.group(1)
            
        # Fallback using hash of URL
        import hashlib
        return hashlib.md5(url.encode()).hexdigest()[:10]

    def find_stock_mentions_with_conversations(
        self, 
        symbol: str, 
        time_filter: str = "month", # Unused mapped to prompt text
        max_results: int = 20, 
        min_comment_score: int = 30, # Unused but kept for compatibility
        company_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Search for high-quality discussions about a stock using Google Search Grounding.
        Returns a list of dictionaries compatible with the social_sentiment table.
        """
        symbol = symbol.upper()
        
        search_query = f"{company_name} ({symbol})" if company_name else symbol
        
        prompt = f"""
        Search Google for the latest "word on the street" investor sentiment and analysis for {search_query} stock on Reddit.
        Find {max_results} specific, high-quality discussion threads from the last {time_filter}.
        Focus on posts with substantial comments and analysis, not just memes.
        
        Return the results as a JSON list of objects strictly.
        Each object must have:
        - title: Post title
        - subreddit: Subreddit name (e.g. 'stocks', 'wallstreetbets', 'valueinvesting')
        - url: Full URL to the thread
        - author: The OP's username (if visible, else 'u/unknown')
        - summary: A decent summary of the main points and top comments (2-3 sentences)
        - sentiment_score: A float from -1.0 (very bearish) to 1.0 (very bullish)
        - score: Estimated number of upvotes (integer, e.g. 150)
        - num_comments: Estimated number of comments (integer, e.g. 45)
        - published_date: The date of the post in YYYY-MM-DD format (or closest estimate)
        
        The 'summary' field should serve as the 'selftext' for display purposes.
        Also create a 'conversation' list with 2-3 key points specifically extracted from the top comments or debate in the thread.
        
        Format:
        [
          {{ 
            "title": "...", 
            "subreddit": "...", 
            "url": "...", 
            "author": "...", 
            "summary": "...", 
            "sentiment_score": 0.8, 
            "score": 100, 
            "num_comments": 50,
            "published_date": "2024-01-01",
            "conversation": ["Point 1", "Point 2"] 
          }}
        ]
        """
        
        try:
            logger.info(f"Searching Google/Reddit for {symbol} sentiment...")
            
            # Enable Google Search tool
            tools = [{'google_search': {}}] 
            
            # Retry logic with fallback model
            models_to_try = [self.model_name, "gemini-2.0-flash"]
            response = None
            
            import time
            
            for model_index, model in enumerate(models_to_try):
                retry_count = 0
                max_retries = 3
                base_delay = 2  # Start with 2s delay
                model_success = False
                
                while retry_count <= max_retries:
                    try:
                        response = self.client.models.generate_content(
                            model=model,
                            contents=prompt,
                            config=GenerateContentConfig(
                                tools=tools,
                                temperature=0.3
                            )
                        )
                        
                        # Check for empty response (common with search grounding sometimes)
                        if not response.text:
                            raise ValueError("Empty response from Gemini (no text generated)")
                            
                        model_success = True
                        break
                    except Exception as e:
                        is_overloaded = "503" in str(e) or "overloaded" in str(e).lower() or "429" in str(e)
                        is_empty_response = "Empty response" in str(e)
                        
                        if (is_overloaded or is_empty_response) and retry_count < max_retries:
                            sleep_time = base_delay * (2 ** retry_count)
                            logger.warning(f"Gemini API ({model}) issue: {str(e)}. Retrying in {sleep_time}s (attempt {retry_count + 1}/{max_retries})")
                            time.sleep(sleep_time)
                            retry_count += 1
                            continue
                        
                        # If failed all retries, try next model if available
                        if model_index < len(models_to_try) - 1:
                            logger.warning(f"Primary model {model} failed (Overloaded or Empty). Switching to fallback...")
                            break
                            
                        # If truly failed (last model), raise
                        logger.error(f"Error calling Gemini ({model}): {e}")
                        raise e
                
                if model_success:
                    break
            
            # Robust JSON parsing
            text = response.text
            if not text:
                logger.warning(f"Empty response from Gemini. Candidates: {response.candidates}")
                print(f"DEBUG: Full Response: {response}")
                return []
                
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
                
            try:
                data = json.loads(text.strip())
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON response: {text[:500]}")
                return []
                
            results = []
            for item in data:
                # Map fields to database schema
                # Schema: id, symbol, source, subreddit, title, selftext, url, author, 
                # score, upvote_ratio, num_comments, sentiment_score, created_utc, published_at
                
                url = item.get('url', '')
                post_id = self._extract_id_from_url(url)
                
                # Parse date
                pub_date_str = item.get('published_date', '')
                published_at = datetime.now()
                created_utc = published_at.timestamp()
                
                try:
                    if pub_date_str:
                        dt = datetime.strptime(pub_date_str, '%Y-%m-%d')
                        published_at = dt
                        created_utc = dt.timestamp()
                except:
                    pass
                
                # Format conversation as expected by frontend/DB (list of dicts usually, but here list of strings is fine if we adapt)
                # DB schema puts 'conversation_json' as JSONB.
                conversation = item.get('conversation', [])
                # Normalize conversation to standard list of objects if needed, or keep as simple strings
                # The legacy format was finding comments. Here we have summaries.
                # Let's wrap them to look like comments for the UI
                
                conversation_objs = []
                for point in conversation:
                    conversation_objs.append({
                        'body': point,
                        'author': 'Summary',
                        'score': 0
                    })
                
                post = {
                    'id': post_id,
                    'symbol': symbol,
                    'source': 'reddit',
                    'subreddit': item.get('subreddit', 'stocks'),
                    'title': item.get('title', 'Untitled'),
                    'selftext': item.get('summary', ''), # Use summary as body
                    'url': url,
                    'author': item.get('author', 'u/unknown'),
                    'score': int(item.get('score', 0)),
                    'upvote_ratio': 1.0, # Unknown
                    'num_comments': int(item.get('num_comments', 0)),
                    'sentiment_score': float(item.get('sentiment_score', 0.0)),
                    'created_utc': created_utc,
                    'published_at': published_at.isoformat(),
                    'conversation': conversation_objs
                }
                results.append(post)
                
            # Sort by date descending (newest first)
            results.sort(key=lambda x: x['created_utc'], reverse=True)

            logger.info(f"Found {len(results)} Reddit threads for {symbol} via Google")
            return results
            
        except Exception as e:
            logger.error(f"Error searching Reddit with Gemini: {e}")
            return []

# Backwards compatibility mock for manual calc if imported elsewhere
def calculate_simple_sentiment(text: str) -> float:
    return 0.0
