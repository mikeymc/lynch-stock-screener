"""
Tests for CLI commands
"""
import pytest
import inspect


class TestCacheCommands:
    """Tests for the CLI cache commands"""
    
    def test_cache_module_imports(self):
        """Verify cache CLI module can be imported"""
        from cli.commands import cache
        assert hasattr(cache, 'app')
    
    def test_cache_commands_registered(self):
        """Verify cache commands are registered"""
        from cli.commands.cache import app
        
        # Check that expected commands exist
        command_names = [cmd.name for cmd in app.registered_commands]
        assert 'prices' in command_names
        assert 'news' in command_names
        assert '10k' in command_names
        assert '8k' in command_names
        assert 'all' in command_names


class TestScreenCommand:
    """Tests for the screen command"""
    
    def test_screen_command_has_region_option(self):
        """Verify screen command has --region option"""
        from cli.commands.screen import start
        
        # Get the function signature
        sig = inspect.signature(start)
        params = list(sig.parameters.keys())
        
        assert 'region' in params
