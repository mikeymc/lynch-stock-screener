# ABOUTME: Utility functions for strategy execution
# ABOUTME: Small helper functions used across strategy execution phases

import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


def log_event(db, run_id: int, message: str):
    """Log an event to the run log."""
    event = {
        'timestamp': datetime.now().isoformat(),
        'message': message
    }
    db.append_to_run_log(run_id, event)
    logger.info(f"[Run {run_id}] {message}")


def get_spy_price(db) -> Optional[float]:
    """Get current SPY price from benchmark snapshots."""
    benchmark = db.get_benchmark_snapshot(date.today())
    return benchmark['spy_price'] if benchmark else None
