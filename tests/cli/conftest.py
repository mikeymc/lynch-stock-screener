# ABOUTME: Pytest fixtures for tests/cli directory
# ABOUTME: Adds project root to Python path for CLI imports

import sys
import os
from unittest.mock import MagicMock
from typing import Any

# Add project root directory to Python path for all CLI test imports
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.abspath(project_root))


# Create a smart typer mock that preserves command structure
class MockTyper:
    """Mock Typer class that tracks registered commands"""

    def __init__(self, **kwargs):
        self.registered_commands = []
        self.help = kwargs.get('help', '')

    def command(self, name=None):
        """Decorator that preserves function and tracks it as a command"""
        def decorator(func):
            # Create a mock command object
            cmd = MagicMock()
            cmd.name = name or func.__name__
            cmd.callback = func
            self.registered_commands.append(cmd)
            return func
        return decorator


class MockOption:
    """Mock for typer.Option that acts as a default value"""

    def __init__(self, default=None, *args, **kwargs):
        self.default = default

    def __repr__(self):
        return f"Option({self.default})"


# Create mock typer module
mock_typer = MagicMock()
mock_typer.Typer = MockTyper
mock_typer.Option = MockOption
mock_typer.Exit = Exception

# Mock CLI dependencies before any CLI imports happen
sys.modules['typer'] = mock_typer
sys.modules['dotenv'] = MagicMock()
