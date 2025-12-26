# ABOUTME: Global rate limiter for SEC API requests
# ABOUTME: Ensures all threads stay within SEC's 10 requests/second limit

import threading
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SECRateLimiter:
    """
    Thread-safe global rate limiter for SEC API requests.
    
    SEC EDGAR has a 10 requests/second limit. This class ensures that
    all threads across the application share a single rate limit.
    
    Uses a simple token bucket algorithm with 1 token = 1 request.
    """
    
    def __init__(self, requests_per_second: float = 8.0):
        """
        Initialize the rate limiter.
        
        Args:
            requests_per_second: Maximum requests per second (default 8 to stay under SEC's 10)
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.lock = threading.Lock()
        self.last_request_time = 0.0
        self.request_count = 0
        
        logger.info(f"SEC Rate Limiter initialized: {requests_per_second} req/sec (interval: {self.min_interval:.3f}s)")
    
    def acquire(self, caller: str = "unknown") -> float:
        """
        Block until it's safe to make a SEC API request.
        
        Args:
            caller: Identifier for logging (e.g., symbol being processed)
            
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
            

            
            return wait_time
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        return {
            'requests_per_second': self.requests_per_second,
            'total_requests': self.request_count,
            'min_interval': self.min_interval
        }


# Global singleton instance - import this in other modules
SEC_RATE_LIMITER = SECRateLimiter(requests_per_second=5.0)


def configure_edgartools_rate_limit():
    """
    Configure the edgartools library to use a compatible rate limit.
    
    edgartools has its own caching/rate limiting via httpx. We configure
    it to be conservative so our global limiter is the bottleneck.
    """
    try:
        from edgar import set_identity
        from edgar.httprequests import rate_limiter
        
        # edgartools uses its own rate limiter - set it to be slightly faster
        # than ours so that our global limiter is the true bottleneck
        # This prevents double-waiting
        if hasattr(rate_limiter, 'set_rate'):
            rate_limiter.set_rate(10)  # Let edgartools think it can do 10/sec
            logger.info("Configured edgartools rate limiter to 10 req/sec")
    except ImportError:
        logger.debug("edgartools rate_limiter not directly accessible")
    except Exception as e:
        logger.warning(f"Could not configure edgartools rate limiter: {e}")
