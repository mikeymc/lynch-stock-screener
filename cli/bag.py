#!/usr/bin/env python3
"""
bag - CLI tool for Lynch Stock Screener
"""
import os
from pathlib import Path
import typer
from rich.console import Console
from dotenv import load_dotenv
from cli.commands import prod, test, screen, cache, server, docs, worktree

# Load .env file from project root
project_root = Path(__file__).parent.parent
dotenv_path = project_root / ".env"
load_dotenv(dotenv_path)

console = Console()
app = typer.Typer(
    name="bag",
    help="🎒 CLI for Lynch Stock Screener - Deploy, test, and manage your stock screening app",
    add_completion=False,
)

# Add command groups
app.add_typer(prod.app, name="prod", help="Production environment operations")
app.add_typer(screen.app, name="screen", help="Stock screening commands")
app.add_typer(cache.app, name="cache", help="Data cache commands (prices, news, 10k, 8k)")
app.add_typer(server.app, name="server", help="Local development server commands")
app.add_typer(docs.app, name="docs", help="Research documentation commands")
app.add_typer(worktree.app, name="worktree", help="Worktree configuration & setup")
app.add_typer(worktree.app, name="worktrees", help="Alias for worktree")

# Add standalone commands
app.command()(test.ship)
app.command()(test.test)


if __name__ == "__main__":
    app()
