# ABOUTME: Package init for cache CLI commands that pre-warm stock detail page data.
# ABOUTME: Creates the Typer app and imports submodules to register all commands.
import typer

app = typer.Typer(help="Cache commands for pre-warming stock detail data")

# Import command modules to trigger registration (app must be defined above first)
from cli.commands.cache import data_commands, content_commands, filing_commands  # noqa: E402, F401

# Re-export command functions for backward compatibility with existing imports
from cli.commands.cache.content_commands import news  # noqa: E402, F401
from cli.commands.cache.filing_commands import ten_k, eight_k  # noqa: E402, F401
