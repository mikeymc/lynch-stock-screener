# ABOUTME: Background worker package for scheduled stock data processing jobs
# ABOUTME: Re-exports BackgroundWorker and utility functions

# CRITICAL: Disable yfinance's SQLite caches BEFORE any other imports
# to prevent "database is locked" errors under concurrent thread access.
# This must be at the very top of the file.
import yfinance.cache as _yf_cache

def _init_dummy_tz_cache(self, cache_dir=None):
    self._cache = _yf_cache._TzCacheDummy()

def _init_dummy_cookie_cache(self, cache_dir=None):
    self._cache = _yf_cache._CookieCacheDummy()

# Monkey-patch the initialise methods to use dummy caches
_yf_cache._TzCacheManager.initialise = _init_dummy_tz_cache
_yf_cache._CookieCacheManager.initialise = _init_dummy_cookie_cache

# Also patch the get_*_cache functions to return global dummy instances immediately
_yf_cache._tz_cache = _yf_cache._TzCacheDummy()
_yf_cache._cookie_cache = _yf_cache._CookieCacheDummy()

# Override the get functions to return our dummy caches
_yf_cache.get_tz_cache = lambda: _yf_cache._tz_cache
_yf_cache.get_cookie_cache = lambda: _yf_cache._cookie_cache

print("[Worker] yfinance SQLite cache disabled (using dummy caches)")
# End yfinance cache patch

# Load environment variables from .env files
from dotenv import load_dotenv
load_dotenv()  # Load from .env in current directory
load_dotenv('../.env')  # Also try parent directory

# CRITICAL: Disable EDGAR caching BEFORE any other imports that use edgartools
from sec_rate_limiter import configure_edgartools_rate_limit
configure_edgartools_rate_limit()

from worker.core import BackgroundWorkerCore, get_memory_mb, check_memory_warning
from worker.data_jobs import DataJobsMixin
from worker.sec_jobs import SECJobsMixin
from worker.content_jobs import ContentJobsMixin
from worker.screening_jobs import ScreeningJobsMixin
from worker.thesis_jobs import ThesisJobsMixin
from worker.alert_jobs import AlertJobsMixin
from worker.portfolio_jobs import PortfolioJobsMixin
from worker.strategy_jobs import StrategyJobsMixin
from worker.main import main


class BackgroundWorker(BackgroundWorkerCore, DataJobsMixin, SECJobsMixin,
                       ContentJobsMixin, ScreeningJobsMixin, ThesisJobsMixin,
                       AlertJobsMixin, PortfolioJobsMixin, StrategyJobsMixin):
    pass
