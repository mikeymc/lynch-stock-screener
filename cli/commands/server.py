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
def start():
    """Start Flask app and worker in separate iTerm windows"""
    
    # Find the project root directory
    project_root = Path(__file__).parent.parent.parent
    backend_dir = project_root / "backend"
    
    if not (backend_dir / "app.py").exists():
        console.print("[bold red]✗ Could not find backend/app.py[/bold red]")
        raise typer.Exit(1)
    
    if not (backend_dir / "worker.py").exists():
        console.print("[bold red]✗ Could not find backend/worker.py[/bold red]")
        raise typer.Exit(1)
    
    console.print("[bold blue]🚀 Starting Flask app and worker in split panes...[/bold blue]")
    
    # AppleScript to split current iTerm pane
    applescript = f'''
tell application "iTerm"
    tell current session of current window
        -- Name and start Flask app in current pane
        set name to "local dev server"
        write text "cd {backend_dir}"
        write text "uv run app.py"
        
        -- Split pane horizontally and start worker
        set newSession to (split horizontally with default profile)
        tell newSession
            set name to "local dev worker"
            write text "cd {backend_dir}"
            write text "uv run python worker.py"
        end tell
    end tell
end tell
'''
    
    try:
        # Execute AppleScript
        subprocess.run(['osascript', '-e', applescript], check=True)
        console.print("[bold green]✓ Started Flask app and worker in split panes[/bold green]")
        console.print("[dim]Flask app: http://localhost:5000 (top pane)[/dim]")
        console.print("[dim]Worker: Processing background jobs (bottom pane)[/dim]")
        console.print()
        console.print("[yellow]Tip: Use Cmd+D to close panes or 'bag server stop' to stop processes[/yellow]")
        
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]✗ Failed to start servers:[/bold red] {e}")
        console.print("[yellow]Make sure you're running this from within iTerm[/yellow]")
        raise typer.Exit(1)


@app.command()
def stop():
    """Stop Flask app and worker processes"""
    
    try:
        # Kill Flask processes
        result1 = subprocess.run(['pkill', '-f', 'npm run dev'], capture_output=True)
        
        # Kill worker processes
        result2 = subprocess.run(['pkill', '-f', 'python worker.py'], capture_output=True)
        
        console.print("[bold green]✓ Stopped all server processes[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]✗ Error stopping servers:[/bold red] {e}")
        raise typer.Exit(1)

