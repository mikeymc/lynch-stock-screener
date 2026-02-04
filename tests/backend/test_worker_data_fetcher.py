# ABOUTME: Tests that BackgroundWorker properly initializes data_fetcher
# ABOUTME: Ensures MaterialEventsFetcher can be created without AttributeError

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from worker import BackgroundWorker


def test_worker_has_data_fetcher_attribute():
    """Test that BackgroundWorker initializes data_fetcher attribute"""
    worker = BackgroundWorker()

    # Should have data_fetcher attribute
    assert hasattr(worker, 'data_fetcher'), "BackgroundWorker should have data_fetcher attribute"
    assert worker.data_fetcher is not None, "data_fetcher should not be None"

    # Verify it's the right type
    from data_fetcher import DataFetcher
    assert isinstance(worker.data_fetcher, DataFetcher), "data_fetcher should be a DataFetcher instance"


def test_worker_data_fetcher_can_be_used_with_material_events():
    """Test that worker's data_fetcher can be passed to MaterialEventsFetcher"""
    from material_events_fetcher import MaterialEventsFetcher
    from sec_8k_client import SEC8KClient
    from edgar_fetcher import EdgarFetcher

    worker = BackgroundWorker()

    # Create minimal SEC8KClient (same as in worker)
    cik_cache = EdgarFetcher.prefetch_cik_cache("test-agent")
    edgar_fetcher = EdgarFetcher(
        user_agent="test-agent",
        db=worker.db,
        cik_cache=cik_cache
    )
    sec_8k_client = SEC8KClient(
        user_agent="test-agent",
        edgar_fetcher=edgar_fetcher
    )

    # This should not raise AttributeError
    events_fetcher = MaterialEventsFetcher(
        worker.db,
        sec_8k_client,
        data_fetcher=worker.data_fetcher
    )

    assert events_fetcher.data_fetcher is not None
    assert events_fetcher.data_fetcher is worker.data_fetcher
