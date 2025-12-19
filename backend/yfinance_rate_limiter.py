# ABOUTME: Rate limiter and timeout protection for yfinance API calls
# ABOUTME: Prevents production hangs from slow/unresponsive Yahoo Finance API

import logging
import time
import socket
from threading import Semaphore
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

# Global semaphore to limit concurrent yfinance API calls
# Reduced to 2 to avoid SQLite lock contention in yfinance's internal cache
YFINANCE_SEMAPHORE = Semaphore(2)

# Default timeout for yfinance API calls (in seconds)
DEFAULT_TIMEOUT = 30

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds


class YFinanceTimeoutError(Exception):
    """Raised when a yfinance API call times out"""
    pass


def with_timeout_and_retry(
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    operation_name: str = "yfinance call"
):
    """
    Decorator to add timeout protection and retry logic to yfinance API calls.
    
    Args:
        timeout: Socket timeout in seconds
        max_retries: Maximum number of retry attempts
        operation_name: Human-readable name for logging
    
    Returns:
        Decorated function with timeout and retry protection
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Extract symbol from args for logging (assumes first arg is self, second is symbol)
            symbol = args[1] if len(args) > 1 else "UNKNOWN"
            
            # Acquire semaphore to limit concurrent calls
            with YFINANCE_SEMAPHORE:
                backoff = INITIAL_BACKOFF
                last_exception = None
                
                for attempt in range(max_retries):
                    try:
                        # Set socket timeout
                        old_timeout = socket.getdefaulttimeout()
                        socket.setdefaulttimeout(timeout)
                        
                        try:
                            logger.info(f"[{symbol}] ▶️  Starting {operation_name} (attempt {attempt + 1}/{max_retries}, timeout={timeout}s)")
                            start_time = time.time()
                            
                            result = func(*args, **kwargs)
                            
                            elapsed = time.time() - start_time
                            logger.info(f"[{symbol}] ✅ Completed {operation_name} in {elapsed:.2f}s")
                            
                            return result
                        finally:
                            # Restore original timeout
                            socket.setdefaulttimeout(old_timeout)
                    
                    except socket.timeout as e:
                        last_exception = e
                        logger.warning(f"[{symbol}] {operation_name} timed out after {timeout}s (attempt {attempt + 1}/{max_retries})")
                        
                        if attempt < max_retries - 1:
                            logger.info(f"[{symbol}] Retrying {operation_name} after {backoff:.1f}s backoff...")
                            time.sleep(backoff)
                            backoff *= 2  # Exponential backoff
                        else:
                            logger.error(f"[{symbol}] {operation_name} failed after {max_retries} attempts")
                    
                    except Exception as e:
                        last_exception = e
                        error_str = str(e).lower()
                        error_type = type(e).__name__
                        
                        # Detect specific error types for better logging
                        if '429' in error_str or 'too many requests' in error_str:
                            logger.warning(f"[{symbol}] ⚠️  RATE LIMITED by Yahoo Finance (HTTP 429) during {operation_name} (attempt {attempt + 1}/{max_retries})")
                        elif '403' in error_str or 'forbidden' in error_str:
                            logger.warning(f"[{symbol}] ⚠️  ACCESS FORBIDDEN by Yahoo Finance (HTTP 403) during {operation_name} - possible IP block (attempt {attempt + 1}/{max_retries})")
                        elif any(code in error_str for code in ['500', '502', '503', '504']):
                            logger.warning(f"[{symbol}] ⚠️  Yahoo Finance SERVER ERROR ({error_type}) during {operation_name} (attempt {attempt + 1}/{max_retries})")
                        elif "404" in error_str or "No data found" in error_str:
                            logger.debug(f"[{symbol}] No data found (404), giving up on {operation_name}")
                            return None
                        else:
                            logger.warning(f"[{symbol}] {operation_name} failed with {error_type}: {e} (attempt {attempt + 1}/{max_retries})")
                        
                        # Don't retry on 404 errors (already handled above)
                        if "404" in error_str or "No data found" in error_str:
                            return None
                        
                        if attempt < max_retries - 1:
                            logger.info(f"[{symbol}] Retrying {operation_name} after {backoff:.1f}s backoff...")
                            time.sleep(backoff)
                            backoff *= 2
                        else:
                            logger.error(f"[{symbol}] {operation_name} failed after {max_retries} attempts")
                
                # All retries exhausted
                logger.error(f"[{symbol}] {operation_name} failed permanently: {last_exception}")
                return None
        
        return wrapper
    return decorator
