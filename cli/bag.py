#!/usr/bin/env python3
"""
bag - CLI tool for Lynch Stock Screener
"""
import os
from pathlib import Path
import typer
from rich.console import Console
from dotenv import load_dotenv
from cli.commands import prod, test, screen, cache

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

# Add standalone commands
app.command()(test.ship)
app.command()(test.test)


if __name__ == "__main__":
    app()
