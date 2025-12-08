"""
Pytest fixtures for backend unit and integration tests.
"""

import sys
import os
import pytest

# Add backend directory to Python path for imports
backend_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
sys.path.insert(0, os.path.abspath(backend_path))


def pytest_collection_modifyitems(items):
    """Automatically add 'backend' marker to all tests in this directory."""
    for item in items:
        if "tests/backend" in str(item.fspath):
            item.add_marker(pytest.mark.backend)
