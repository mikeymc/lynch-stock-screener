# ABOUTME: Provides timeout wrapper for blocking operations like yfinance API calls
# ABOUTME: Uses threading to enforce time limits on function execution

import threading
import logging
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TimeoutError(Exception):
    """Raised when a function call exceeds its timeout"""
    pass


def with_timeout(timeout_seconds: float, default: Optional[Any] = None) -> Callable:
    """
    Decorator to add timeout protection to a function call

    Args:
        timeout_seconds: Maximum seconds to wait for function completion
        default: Value to return if timeout occurs (if None, raises TimeoutError)

    Returns:
        Decorated function that will timeout after specified seconds

    Example:
        @with_timeout(10, default={})
        def fetch_data():
            return slow_api_call()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            result = [TimeoutError("Function call timed out")]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    result[0] = e

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout_seconds)

            if thread.is_alive():
                # Timeout occurred
                logger.warning(f"{func.__name__} timed out after {timeout_seconds}s")
                if default is not None:
                    return default
                raise TimeoutError(f"{func.__name__} exceeded timeout of {timeout_seconds}s")

            # Check if an exception occurred
            if isinstance(result[0], Exception):
                raise result[0]

            return result[0]

        return wrapper
    return decorator


def call_with_timeout(func: Callable[..., T], timeout_seconds: float, default: Optional[T] = None, *args, **kwargs) -> T:
    """
    Call a function with a timeout

    Args:
        func: Function to call
        timeout_seconds: Maximum seconds to wait
        default: Value to return if timeout occurs (if None, raises TimeoutError)
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result of func() or default if timeout

    Example:
        result = call_with_timeout(yf.Ticker, 10, default=None, 'AAPL')
    """
    result = [TimeoutError("Function call timed out")]

    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            result[0] = e

    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Timeout occurred
        logger.warning(f"{func.__name__} timed out after {timeout_seconds}s")
        if default is not None:
            return default
        raise TimeoutError(f"{func.__name__} exceeded timeout of {timeout_seconds}s")

    # Check if an exception occurred
    if isinstance(result[0], Exception):
        raise result[0]

    return result[0]
