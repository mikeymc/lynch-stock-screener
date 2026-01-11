import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Manage git worktrees for independent development environments")

from cli.commands.app_cmd import start_app_logic, kill_processes_in_dir





def run_command(cmd: str, cwd: Path, description: str):
    """Run a shell command and print status"""
    console.print(f"[dim]Running: {description}...[/dim]")
    try:
        subprocess.run(cmd, shell=True, check=True, cwd=cwd, capture_output=True)
        console.print(f"[green]✓ {description}[/green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ Failed: {description}[/red]")
        console.print(f"[red]Error: {e.stderr.decode()}[/red]")
        # We don't exit here immediately to allow partial setups, but for initialize? 
        # Actually initialize should probably fail fast.
        raise typer.Exit(1)

@app.command("init", help="Alias for initialize")
def init(name: str):
    """
    Alias for initialize.
    """
    initialize(name)

@app.command()
def initialize(name: str):
    """
    Initialize a new git worktree with full environment setup.
    
    1. Creates git worktree
    2. Sets up Python venv with uv
    3. Installs dependencies (root & backend)
    4. Installs frontend node modules
    5. Copies .env files
    6. Launches backend, worker, and frontend on unique ports
    """
    # Determine repo root securely based on this file's location
    # cli/commands/worktree.py -> cli/commands -> cli -> root
    repo_root = Path(__file__).resolve().parent.parent.parent
    console.print(f"[dim]Repo root detected at: {repo_root}[/dim]")

    # verify we are in the repo (look for .git or .agent)
    if not (repo_root / ".git").exists() and not (repo_root.parent / ".git").exists():
         # In a worktree, .git is a file. In main repo, it's a dir.
         # But usually we run this from main repo.
         pass
    
    # Check if we are in a subfolder, move to root
    # Ideally user usually runs 'bag' from anywhere, but let's assume root for now or find it.
    # bag.py finds root via __file__. Let's assume Path.cwd() is okay for the 'git worktree' command
    # but strictly 'git worktree add' should be run from inside a git repo.
    
    # 1. Create worktree
    # The worktree will be created at ../<name>
    worktree_path = repo_root.parent / name
    
    if worktree_path.exists():
        console.print(f"[yellow]Warning: path {worktree_path} already exists.[/yellow]")
        if not typer.confirm("Do you want to proceed and potentially overwrite/use existing?"):
            raise typer.Exit()
    else:
        # We need to run git worktree add
        # "git worktree add ../<name> -b <name>"
        cmd = f"git worktree add ../{name} -b {name}"
        console.print(f"[bold blue]Step 1: Creating worktree '{name}'...[/bold blue]")
        # We run this from the current repo (cwd)
        try:
             subprocess.run(cmd, shell=True, check=True, cwd=repo_root)
             console.print(f"[green]✓ Worktree created at {worktree_path}[/green]")
        except subprocess.CalledProcessError:
             console.print("[red]Failed to create worktree. Ensure you are in the git repository and branch name is valid.[/red]")
             raise typer.Exit(1)

    # 2. Setup uv venv
    console.print(f"[bold blue]Step 2: Setting up Python environment (uv)...[/bold blue]")
    run_command("uv venv", worktree_path, "Create virtual environment")
    
    # 3. Install dependencies
    console.print(f"[bold blue]Step 3: Installing dependencies...[/bold blue]")
    run_command("uv pip install -r requirements.txt", worktree_path, "Install root requirements")
    
    backend_dir = worktree_path / "backend"
    if backend_dir.exists():
        run_command("uv pip install -r requirements.txt", backend_dir, "Install backend requirements")
    
    # 4. Frontend Install
    frontend_dir = worktree_path / "frontend"
    if frontend_dir.exists():
        console.print(f"[bold blue]Step 4: Installing frontend modules...[/bold blue]")
        run_command("npm install", frontend_dir, "Install node modules")

    # 5. Copy .env files
    console.print(f"[bold blue]Step 5: Copying configuration...[/bold blue]")
    
    # Root .env
    src_env = repo_root / ".env"
    dst_env = worktree_path / ".env"
    if src_env.exists():
        shutil.copy(src_env, dst_env)
        console.print("[dim]Copied root .env[/dim]")
    
    # Backend .env
    src_be_env = repo_root / "backend" / ".env"
    dst_be_env = worktree_path / "backend" / ".env"
    if src_be_env.exists():
        shutil.copy(src_be_env, dst_be_env)
        console.print("[dim]Copied backend/.env[/dim]")

    # 5b. Copy other critical config files (that might be ignored by git)
    config_files = [
        "frontend/tsconfig.json",
        "frontend/tsconfig.node.json",
        "frontend/components.json",
    ]
    
    for config_file in config_files:
        src = repo_root / config_file
        dst = worktree_path / config_file
        if src.exists():
            shutil.copy(src, dst)
            console.print(f"[dim]Copied {config_file}[/dim]")

    # 5c. Copy frontend/src/lib if it exists in root but not in worktree (usually due to gitignore)
    # This addresses the "missing @/lib/utils" error
    src_lib = repo_root / "frontend/src/lib"
    dst_lib = worktree_path / "frontend/src/lib"
    if src_lib.exists():
        if not dst_lib.exists():
            shutil.copytree(src_lib, dst_lib)
            console.print(f"[dim]Copied frontend/src/lib/ (was untracked)[/dim]")
        



    # 6 & 7. Launch (Find Ports & Start)
    # start_app_logic(name, worktree_path) # Logic is now shared but we don't want to block init
    
    console.print(f"\n[bold green]Worktree '{name}' initialized successfully![/bold green]")
    console.print(f"\n[yellow]To launch the app:[/yellow]")
    console.print(f"  cd ../{name}")
    console.print(f"  bag app start")

    

@app.command("list")
def list_worktrees():
    """
    List all active git worktrees.
    """
    from rich.table import Table
    
    repo_root = Path(__file__).resolve().parent.parent.parent
    
    try:
        result = subprocess.run(["git", "worktree", "list", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
        worktrees = result.stdout.strip().split("\n\n")
        
        table = Table(title="Git Worktrees")
        table.add_column("Name", style="cyan")
        table.add_column("Branch", style="green")
        table.add_column("Path", style="dim")
        table.add_column("HEAD", style="magenta")
        
        for wt in worktrees:
            lines = wt.splitlines()
            wt_path = "Unknown"
            wt_branch = "Headless/Detached"
            wt_head = "Unknown"
            
            for line in lines:
                if line.startswith("worktree "):
                    wt_path = line.split(" ", 1)[1]
                elif line.startswith("branch "):
                    wt_branch = line.split("refs/heads/", 1)[1] if "refs/heads/" in line else line.split(" ", 1)[1]
                elif line.startswith("HEAD "):
                    wt_head = line.split(" ", 1)[1][:7]
            
            name = Path(wt_path).name
            table.add_row(name, wt_branch, wt_path, wt_head)
            
        console.print(table)
        
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to list worktrees: {e}[/red]")


@app.command()
def remove(name: str, force: bool = typer.Option(False, "--force", "-f", help="Force removal even if dirty")):
    """
    Teardown a worktree: kill processes, remove folder, delete branch.
    """

    # 1. Locate worktree
    # Instead of guessing the path, let's ask git where it is.
    repo_root = Path(__file__).resolve().parent.parent.parent
    
    # Check if a worktree with this name exists in git
    try:
        result = subprocess.run(["git", "worktree", "list", "--porcelain"], capture_output=True, text=True, cwd=repo_root)
        worktrees = result.stdout.strip().split("\n\n")
        
        target_path = None
        for wt in worktrees:
            lines = wt.splitlines()
            wt_path = None
            wt_branch = None
            for line in lines:
                if line.startswith("worktree "):
                    wt_path = line.split(" ", 1)[1]
                if line.startswith("branch "):
                    wt_branch = line.split("refs/heads/", 1)[1] if "refs/heads/" in line else line.split(" ", 1)[1]
                    
            # Match by name (folder name or branch name?)
            # Usually name passed is directory name.
            if wt_path and Path(wt_path).name == name:
                target_path = Path(wt_path)
                break
            # Also try matching by branch name if folder name differs?
            if wt_branch and wt_branch == name:
                 target_path = Path(wt_path)
                 break
                 
        if target_path:
            worktree_path = target_path
            console.print(f"[dim]Found worktree at: {worktree_path}[/dim]")
        else:
             # Fallback to sibling assumption if not found (maybe it was deleted but process still running?)
             worktree_path = repo_root.parent / name
             console.print(f"[dim]Worktree not found in git, checking path: {worktree_path}[/dim]")

    except Exception as e:
        console.print(f"[red]Error finding worktree: {e}[/red]")
        worktree_path = repo_root.parent / name
    
    if not worktree_path.exists():
        # If it's also not in git (target_path is None), then it really doesn't exist.
        if target_path is None:
             console.print(f"[red]Error: Worktree '{name}' not found in git and path {worktree_path} does not exist.[/red]")
             console.print(f"[yellow]Use 'bag worktrees list' to see available worktrees.[/yellow]")
             raise typer.Exit(1)
        else:
             console.print(f"[yellow]Warning: Worktree folder {worktree_path} is missing, but it is registered in git.[/yellow]")
             if typer.confirm("Do you want to run 'git worktree prune' to clean up this stale entry?"):
                 subprocess.run(["git", "worktree", "prune"], check=True, cwd=repo_root)
                 console.print("[green]✓ Pruned stale worktrees[/green]")
                 # We are done since folder is gone and git is cleaned
                 return
             else:
                 console.print("[red]Aborting manual cleanup.[/red]")
                 raise typer.Exit(1)

    if not force:
        if not typer.confirm(f"Are you sure you want to completely remove worktree '{name}'?"):
            raise typer.Exit()

    # 2. Kill processes
    if worktree_path.exists():
        kill_processes_in_dir(worktree_path)

    # 3. Git Worktree Remove
    console.print(f"[bold blue]Removing worktree '{name}'...[/bold blue]")
    try:
        # Check status first?
        # git worktree remove <path>
        # If dirty, it will fail.
        
        cmd = ["git", "worktree", "remove", str(worktree_path)]
        if force:
            cmd.append("--force")
            
        subprocess.run(cmd, check=True, cwd=repo_root)
        console.print("[green]✓ Worktree removed from git[/green]")
        
    except subprocess.CalledProcessError:
        if not force:
            console.print("[yellow]Worktree has uncommitted changes or is dirty.[/yellow]")
            if typer.confirm("Do you want to FORCE remove it? (This will lose uncommitted changes)"):
                 subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], check=True, cwd=repo_root)
                 console.print("[green]✓ Worktree force removed[/green]")
            else:
                 console.print("[red]Aborted.[/red]")
                 raise typer.Exit(1)
        else:
             console.print("[red]Failed to remove worktree even with force.[/red]")
             raise typer.Exit(1)
             
    # 4. Folder cleanup (git worktree remove usually does this, but maybe not if force killed?)
    if worktree_path.exists():
        try:
            shutil.rmtree(worktree_path)
            console.print("[green]✓ Directory cleaned up[/green]")
        except OSError as e:
            console.print(f"[red]Warning: Could not remove directory {worktree_path}: {e}[/red]")

    # 5. Delete Branch
    # git branch -D <name>
    console.print(f"[bold blue]Deleting branch '{name}'...[/bold blue]")
    try:
        # The branch name is usually the same as worktree name (if created via our init command)
        subprocess.run(["git", "branch", "-d", name], check=False, cwd=repo_root, capture_output=True)
        # If -d fails (unmerged), prompt?
        # Usually -D is what we want for a throwaway dev branch.
        # But 'bag worktree init' creates it off main?
        
        # Let's try -D if valid
        subprocess.run(["git", "branch", "-D", name], check=True, cwd=repo_root, capture_output=True)
        console.print(f"[green]✓ Branch '{name}' deleted[/green]")
    except subprocess.CalledProcessError:
        console.print(f"[yellow]Warning: Could not delete branch '{name}'. It might not exist or be checked out elsewhere.[/yellow]")
        
    console.print(f"\n[bold green]Teardown complete for '{name}'![/bold green]")

