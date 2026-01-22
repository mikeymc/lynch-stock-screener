"""
Database commands for bag CLI
"""
import typer
import os
import signal
import subprocess
import time
from pathlib import Path
from rich.console import Console
from cli.utils.fly import run_fly_command

console = Console()
app = typer.Typer(help="Database operations")



PID_FILE = Path("/tmp/bag_db_proxy.pid")
LOG_FILE = Path("/tmp/bag_db_proxy.log")


@app.command()
def connect():
    """Connect to Postgres database"""
    console.print("[bold blue]🗄️  Connecting to database...[/bold blue]")
    run_fly_command(["postgres", "connect", "-a", "lynch-postgres"])


@app.command("start")
def start(
    port: int = typer.Option(15432, help="Local port to proxy to"),
    db_port: int = typer.Option(5432, help="Remote database port"),
):
    """Start the database proxy in the background"""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            # Check if process is still running
            os.kill(pid, 0)
            console.print(f"[yellow]Proxy already running (PID: {pid}). Use 'stop' first.[/yellow]")
            return
        except (OSError, ValueError):
            # Stale PID file
            console.print("[yellow]Found stale PID file. Cleaning up...[/yellow]")
            PID_FILE.unlink(missing_ok=True)

    console.print(f"[bold blue]🔌 Starting proxy lynch-postgres:{db_port} -> local:{port}...[/bold blue]")
    
    # Open log file
    log_f = open(LOG_FILE, "w")
    
    try:
        process = subprocess.Popen(
            ["flyctl", "proxy", f"{port}:{db_port}", "-a", "lynch-postgres"],
            stdout=log_f,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid  # Detach from terminal
        )
        
        # Write PID
        PID_FILE.write_text(str(process.pid))
        
        # Wait a moment to check for immediate failure
        time.sleep(1)
        if process.poll() is not None:
            # It crashed
            console.print(f"[bold red]❌ Proxy failed to start. Check logs at {LOG_FILE}[/bold red]")
            # Show last few lines of log
            with open(LOG_FILE, "r") as f:
                print(f.read())
            PID_FILE.unlink(missing_ok=True)
            raise typer.Exit(1)
            
        console.print(f"[bold green]✓ Proxy running in background (PID: {process.pid})[/bold green]")
        console.print(f"[dim]Logs: {LOG_FILE}[/dim]")
        
    except Exception as e:
        console.print(f"[bold red]Error starting proxy: {e}[/bold red]")
        if PID_FILE.exists():
            PID_FILE.unlink()


@app.command("stop")
def stop():
    """Stop the running database proxy"""
    if not PID_FILE.exists():
        console.print("[yellow]No proxy running (PID file not found).[/yellow]")
        return
        
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        console.print(f"[bold green]✓ Stopped proxy (PID: {pid})[/bold green]")
    except ProcessLookupError:
        console.print("[yellow]Process not found. Cleaning up PID file.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]Error stopping proxy: {e}[/bold red]")
    finally:
        PID_FILE.unlink(missing_ok=True)


@app.command("status")
def status():
    """Check status of the database proxy"""
    if not PID_FILE.exists():
        console.print("[red]Proxy is not running[/red]")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0) # Check if running
        console.print(f"[bold green]✓ Proxy is running (PID: {pid})[/bold green]")
        console.print(f"[dim]Log file: {LOG_FILE}[/dim]")
    except (OSError, ValueError):
        console.print("[red]PID file exists but process is not running (stale).[/red]")
        PID_FILE.unlink(missing_ok=True)
