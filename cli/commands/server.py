# ABOUTME: CLI commands for local development server management
# ABOUTME: Provides 'bag server start' to run the Flask dev server with proper logging

import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Local development server commands")


@app.command()
def start(
    port: int = typer.Option(5001, "--port", "-p", help="Port to run the server on"),
    debug: bool = typer.Option(True, "--debug/--no-debug", help="Run in debug mode"),
):
    """Start the local Flask development server with full logging"""
    
    # Find the backend directory
    project_root = Path(__file__).parent.parent.parent
    backend_dir = project_root / "backend"
    
    if not (backend_dir / "app.py").exists():
        console.print("[bold red]✗ Could not find backend/app.py[/bold red]")
        raise typer.Exit(1)
    
    console.print(f"[bold blue]🚀 Starting local server on port {port}...[/bold blue]")
    console.print(f"[dim]Backend directory: {backend_dir}[/dim]")
    console.print()
    
    # Set environment variables for unbuffered output and full logging
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["FLASK_DEBUG"] = "1" if debug else "0"
    
    try:
        # Run the Flask app with uv
        subprocess.run(
            ["uv", "run", "app.py"],
            cwd=backend_dir,
            env=env,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")
    except FileNotFoundError:
        console.print("[bold red]✗ 'uv' not found. Please install uv first.[/bold red]")
        raise typer.Exit(1)
