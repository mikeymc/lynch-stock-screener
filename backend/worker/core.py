# ABOUTME: Core BackgroundWorker class with initialization, run loop, and job dispatch
# ABOUTME: Contains __init__, run, _execute_job, _send_heartbeat, and memory utilities

import os
import time
import signal
import logging
import socket
import resource
import platform
from typing import Dict, Any

from price_history_fetcher import PriceHistoryFetcher
from sec_data_fetcher import SECDataFetcher
from news_fetcher import NewsFetcher
from material_events_fetcher import MaterialEventsFetcher
from dividend_manager import DividendManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Suppress verbose HTTP and SEC library logs
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('edgar').setLevel(logging.WARNING)
logging.getLogger('edgar.httprequests').setLevel(logging.WARNING)
logging.getLogger('hpack').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Configuration
IDLE_SHUTDOWN_SECONDS = int(os.environ.get('WORKER_IDLE_TIMEOUT', 300))  # 5 minutes
HEARTBEAT_INTERVAL = 60  # Extend claim every 60 seconds
POLL_INTERVAL = 5  # Check for new jobs every 5 seconds


def get_memory_mb() -> float:
    """Get current RSS memory usage in MB"""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # macOS returns bytes, Linux returns KB
    if platform.system() == 'Darwin':
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024


# Memory alerting thresholds (based on 4GB worker allocation)
MEMORY_WARNING_MB = 3200   # 80% of 4GB - log warning
MEMORY_CRITICAL_MB = 3800  # 95% of 4GB - log critical


def check_memory_warning(context: str = "") -> None:
    """
    Check memory usage and log warnings if approaching limits.
    Call this periodically during long-running jobs.
    """
    used_mb = get_memory_mb()

    if used_mb >= MEMORY_CRITICAL_MB:
        logger.critical(
            f"🚨 CRITICAL MEMORY: {used_mb:.0f}MB used (limit ~4096MB) - OOM risk! {context}"
        )
    elif used_mb >= MEMORY_WARNING_MB:
        logger.warning(
            f"⚠️ HIGH MEMORY: {used_mb:.0f}MB used (warning threshold: {MEMORY_WARNING_MB}MB) {context}"
        )



class BackgroundWorkerCore:
    """Background worker that polls for and executes jobs from PostgreSQL"""

    def __init__(self):
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}"
        self.shutdown_requested = False
        self.current_job_id = None
        self.last_job_time = time.time()
        self.last_heartbeat = time.time()

        # Initialize database connection
        from database import Database
        self.db = Database(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=int(os.environ.get('DB_PORT', 5432)),
            database=os.environ.get('DB_NAME', 'lynch_stocks'),
            user=os.environ.get('DB_USER', 'lynch'),
            password=os.environ.get('DB_PASSWORD', 'lynch_dev_password')
        )

        # LLM client for alert evaluation (lazy initialized)
        self._llm_client = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        # Initialize Dividend Manager
        self.dividend_manager = DividendManager(self.db)

        # Initialize Data Fetcher
        from data_fetcher import DataFetcher
        self.data_fetcher = DataFetcher(self.db)

        # Worker tier (default to light)
        self.tier = os.environ.get('WORKER_TIER', 'light')

        logger.info(f"Worker {self.worker_id} initialized (Tier: {self.tier})")

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal gracefully"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_requested = True

        # Release current job back to pending if we have one
        if self.current_job_id:
            logger.info(f"Releasing job {self.current_job_id} back to pending")
            self.db.release_job(self.current_job_id)

    @property
    def llm_client(self):
        """Lazy initialization of Gemini client."""
        if self._llm_client is None:
            from google import genai
            self._llm_client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
        return self._llm_client

    def run(self):
        """Main worker loop"""
        logger.info(f"Worker {self.worker_id} starting main loop (Tier: {self.tier})")
        if IDLE_SHUTDOWN_SECONDS > 0:
            logger.info(f"Idle shutdown: {IDLE_SHUTDOWN_SECONDS}s, Poll interval: {POLL_INTERVAL}s")
        else:
            logger.info(f"Idle shutdown: DISABLED, Poll interval: {POLL_INTERVAL}s")

        while not self.shutdown_requested:
            # Check for idle shutdown (skip if IDLE_SHUTDOWN_SECONDS is 0)
            if IDLE_SHUTDOWN_SECONDS > 0:
                idle_time = time.time() - self.last_job_time
                if idle_time > IDLE_SHUTDOWN_SECONDS:
                    logger.info(f"Idle for {idle_time:.0f}s (limit: {IDLE_SHUTDOWN_SECONDS}s), shutting down")
                    break

            # Try to claim a job (filtered by tier)
            job = self.db.claim_pending_job(self.worker_id, tier=self.tier)

            if job:
                self.current_job_id = job['id']
                logger.info(f"Claimed job {job['id']} (type: {job['job_type']})")

                try:
                    self._execute_job(job)
                except Exception as e:
                    logger.error(f"Job {job['id']} failed: {e}")
                    import traceback
                    traceback.print_exc()
                    self.db.fail_job(job['id'], str(e))
                finally:
                    self.current_job_id = None
                    # Reset idle timer AFTER job completes, not when claimed
                    self.last_job_time = time.time()
            else:
                # No jobs available, wait before polling again
                time.sleep(POLL_INTERVAL)

        logger.info(f"Worker {self.worker_id} shutting down")

    def _execute_job(self, job: Dict[str, Any]):
        """Execute a job based on its type"""
        job_id = job['id']
        job_type = job['job_type']
        params = job['params']

        # Mark job as running
        self.db.update_job_status(job_id, 'running')

        if job_type == 'full_screening':
            self._run_screening(job_id, params)
        elif job_type == 'sec_refresh':
            self._run_sec_refresh(job_id, params)
        elif job_type == 'price_history_cache':
            self._run_price_history_cache(job_id, params)
        elif job_type == 'news_cache':
            self._run_news_cache(job_id, params)
        elif job_type == '10k_cache':
            self._run_10k_cache(job_id, params)
        elif job_type == '8k_cache':
            self._run_8k_cache(job_id, params)
        elif job_type == 'form4_cache':
            self._run_form4_cache(job_id, params)
        elif job_type == 'outlook_cache':
            self._run_outlook_cache(job_id, params)
        elif job_type == 'transcript_cache':
            self._run_transcript_cache(job_id, params)
        elif job_type == 'check_alerts':
            self._run_check_alerts(job_id, params)
        elif job_type == 'forward_metrics_cache':
            self._run_forward_metrics_cache(job_id, params)
        elif job_type == 'price_update':
            self._run_price_update(job_id, params)
        elif job_type == 'process_dividends':
            self._run_process_dividends(job_id, params)
        elif job_type == 'strategy_execution':
            self._run_strategy_execution(job_id, params)
        elif job_type == 'thesis_refresher':
            self._run_thesis_refresher(job_id, params)
        elif job_type == 'benchmark_snapshot':
            self._run_benchmark_snapshot(job_id, params)
        elif job_type == 'historical_fundamentals_cache':
            self._run_historical_fundamentals_cache(job_id, params)
        elif job_type == 'quarterly_fundamentals_cache':
            self._run_quarterly_fundamentals_cache(job_id, params)
        else:
            raise ValueError(f"Unknown job type: {job_type}")

    def _send_heartbeat(self, job_id: int):
        """Send heartbeat to extend job claim"""
        now = time.time()
        if now - self.last_heartbeat > 30:  # Every 30 seconds
            self.db.update_job_heartbeat(job_id)
            self.last_heartbeat = now
