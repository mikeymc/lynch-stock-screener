import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional
import threading
import signal
import sys
import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Manage the application runtime")

def find_free_port(start_port: int, max_tries: int = 100) -> int:
    """Find a free port starting from start_port"""
    port = start_port
    checked = 0
    while checked < max_tries:
        # TIMEOUT: Set a timeout so we don't hang if connect takes long
        # HOST: Use 127.0.0.1 to avoid ambiguous localhost resolution
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # Returns 0 on success (port in use), errno on failure (port likely free)
            result = s.connect_ex(('127.0.0.1', port))
            if result != 0:
                return port
        port += 1
        checked += 1
        
    console.print(f"[red]Could not find a free port after checking {max_tries} ports starting at {start_port}[/red]")
    raise typer.Exit(1)

def find_project_root(start_path: Path) -> Path:
    """
    Find the project root by looking for markers like .git, or backend/frontend dirs.
    """
    current = start_path.resolve()
    for _ in range(10): # Max depth
        if (current / ".git").exists() or (current / "backend").exists():
            return current
        if current.parent == current:
            break
        current = current.parent
    
    # Fallback/Debug
    console.print(f"[yellow]Could not detect project root from {start_path}. Assuming current directory.[/yellow]")
    return start_path

def stream_logs(process: subprocess.Popen, prefix: str, style: str):
    """
    Stream logs from a subprocess to the console with a prefix.
    """
    for line in iter(process.stdout.readline, ''):
        console.print(f"[{style}]{prefix}[/{style}] {line.strip()}")
    process.stdout.close()

def start_app_logic(name: str, root_dir: Path, backend_port: Optional[int] = None, frontend_port: Optional[int] = None):
    """
    Shared logic to start the app components (backend, worker, frontend) as background subprocesses
    and stream their logs to the console.
    """
    backend_dir = root_dir / "backend"
    frontend_dir = root_dir / "frontend"
    
    # Check if dirs exist
    if not backend_dir.exists():
        console.print(f"[red]Backend directory not found at {backend_dir}[/red]")
        raise typer.Exit(1)
        
    # Find ports if not provided
    if backend_port is None:
        console.print(f"[dim]Finding backend port...[/dim]")
        # User has whitelisted 5001-5005 for OAuth
        backend_port = find_free_port(5001)
    
    if frontend_port is None:
        console.print(f"[dim]Finding frontend port...[/dim]")
        # Start searching from fairly safe range
        frontend_port = find_free_port(5200)

    console.print(f"[green]Backend Port: {backend_port}[/green]")
    console.print(f"[green]Frontend Port: {frontend_port}[/green]")
    
    # Launch
    console.print(f"[bold blue]Launching applications...[/bold blue]")
    console.print(f"[yellow]Press Ctrl+C to stop all services.[/yellow]")

    # Environment variables
    # Environment variables
    env = os.environ.copy()
    env["PORT"] = str(backend_port)
    env["VITE_API_URL"] = f"http://localhost:{backend_port}"
    env["FRONTEND_URL"] = f"http://localhost:{frontend_port}"
    
    processes = []
    threads = []
    
    try:
        # 1. Backend
        backend_cmd = ["uv", "run", "app.py"]
        console.print(f"[dim]Starting Backend...[/dim]")
        be_proc = subprocess.Popen(
            backend_cmd, 
            cwd=backend_dir, 
            env=env, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1
        )
        processes.append(be_proc)
        t_be = threading.Thread(target=stream_logs, args=(be_proc, "Backend", "cyan"))
        t_be.daemon = True
        t_be.start()
        threads.append(t_be)

        # 2. Worker
        worker_cmd = ["uv", "run", "python", "worker.py"]
        console.print(f"[dim]Starting Worker...[/dim]")
        worker_proc = subprocess.Popen(
            worker_cmd, 
            cwd=backend_dir, 
            env=env, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1
        )
        processes.append(worker_proc)
        t_worker = threading.Thread(target=stream_logs, args=(worker_proc, "Worker", "magenta"))
        t_worker.daemon = True
        t_worker.start()
        threads.append(t_worker)

        # 3. Frontend
        # npm run dev -- --port {frontend_port}
        frontend_cmd = ["npm", "run", "dev", "--", "--port", str(frontend_port)]
        console.print(f"[dim]Starting Frontend...[/dim]")
        fe_proc = subprocess.Popen(
            frontend_cmd, 
            cwd=frontend_dir, 
            env=env, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1
        )
        processes.append(fe_proc)
        t_fe = threading.Thread(target=stream_logs, args=(fe_proc, "Frontend", "green"))
        t_fe.daemon = True
        t_fe.start()
        threads.append(t_fe)
        
        console.print(f"[bold green]Services started! Frontend: http://localhost:{frontend_port}[/bold green]")

        # Keep main thread alive
        while True:
            time.sleep(1)
            # Check if any process died
            if be_proc.poll() is not None:
                console.print("[red]Backend died![/red]")
                break
            if fe_proc.poll() is not None:
                console.print("[red]Frontend died![/red]")
                break

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping services...[/yellow]")
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill()
        console.print("[green]Shutdown complete.[/green]")

@app.command("start")
def start(name: str = typer.Argument("lynch-app", help="Name for the terminal session"),
          port: Optional[int] = typer.Option(None, help="Specific backend port to use"),
          fe_port: Optional[int] = typer.Option(None, help="Specific frontend port to use")):
    """
    Start the application (Backend, Worker, Frontend) in the current directory.
    Streams logs to the console. Press Ctrl+C to stop.
    """
    # Find root from CWD
    root_dir = find_project_root(Path.cwd())
    
    console.print(f"[dim]Starting app in {root_dir}[/dim]")
    
    start_app_logic(name, root_dir, backend_port=port, frontend_port=fe_port)

def kill_processes_in_dir(directory: Path):
    """Find and kill processes running from the given directory"""
    console.print(f"[dim]Checking for processes running in {directory}...[/dim]")
    try:
        # lsof +D <dir> lists open files in directory. We want processes where cwd is inside.
        # Actually lsof is good but slow. 
        # `lsof +D <dir>` might return many things.
        # Let's try finding processes via their cwd using lsof (or pgrep/pwdx on linux, but on mac lsof is best)
        # lsof -F p -d cwd +D <dir>
        
        # Simple approach: lsof +D returns all open files.
        # We specifically want to kill servers (python, node).
        
        result = subprocess.run(['lsof', '-t', '+D', str(directory)], capture_output=True, text=True)
        pids = result.stdout.strip().split('\n')
        pids = [p for p in pids if p] # filter empty
        
        if pids:
            console.print(f"[yellow]Found {len(pids)} processes using this worktree. Terminating...[/yellow]")
            for pid in pids:
                try:
                    # Send SIGTERM
                    os.kill(int(pid), 15)
                except ProcessLookupError:
                    pass
            
            # Wait a bit
            time.sleep(1)
            
            # Force kill if still alive?
            # Re-check
            result = subprocess.run(['lsof', '-t', '+D', str(directory)], capture_output=True, text=True)
            remaining = [p for p in result.stdout.strip().split('\n') if p]
            if remaining:
               console.print(f"[red]Force killing {len(remaining)} stubborn processes...[/red]")
               for pid in remaining:
                   try:
                       os.kill(int(pid), 9)
                   except:
                       pass
            console.print("[green]Processes terminated.[/green]")
        else:
            console.print("[dim]No active processes found.[/dim]")
            
    except FileNotFoundError:
        # lsof might not be in path?
        console.print("[yellow]Warning: 'lsof' not found. Could not auto-terminate processes.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error killing processes: {e}[/red]")


@app.command("stop")
def stop():
    """
    Stop applications running in the current directory.
    """
    root_dir = find_project_root(Path.cwd())
    console.print(f"[bold blue]Stopping app in {root_dir}...[/bold blue]")
    kill_processes_in_dir(root_dir)
