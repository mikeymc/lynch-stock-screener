"""
Testing and shipping commands for bag CLI
"""
import subprocess
import typer
from pathlib import Path
from rich.console import Console

console = Console()

# Get the project root directory (parent of cli/)
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
TESTS_DIR = PROJECT_ROOT / "tests"


def test(
    file: str = typer.Option(None, "--file", "-f", help="Test specific file"),
    match: str = typer.Option(None, "--match", "-k", help="Run tests matching pattern"),
):
    """Run pytest tests"""
    cmd = ["uv", "run", "pytest"]
    
    if file:
        cmd.append(file)
    else:
        # Run backend tests by default (cli/e2e can be run with -f flag)
        cmd.append(str(TESTS_DIR / "backend"))
    
    # Use -p no:cov to fully disable coverage plugin (fixes rich import conflict)
    cmd.extend(["-v", "--tb=short", "-p", "no:cov"])
    
    if match:
        cmd.extend(["-k", match])
    
    console.print(f"[bold blue]🧪 Running tests...[/bold blue]")
    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]\n")
    
    # Run from backend/ directory to avoid Python path conflicts with rich module
    backend_dir = PROJECT_ROOT / "backend"
    result = subprocess.run(cmd, cwd=str(backend_dir))
    
    if result.returncode == 0:
        console.print("\n[bold green]✓ All tests passed![/bold green]")
    else:
        console.print("\n[bold red]✗ Tests failed[/bold red]")
        raise typer.Exit(1)


def ship():
    """Run tests, then git push if tests pass"""
    console.print("[bold blue]🚢 Shipping...[/bold blue]\n")
    
    # Run tests first
    console.print("[bold]Step 1: Running tests[/bold]")
    cmd = ["uv", "run", "pytest", str(TESTS_DIR), "-v", "--tb=short"]
    result = subprocess.run(cmd)
    
    if result.returncode != 0:
        console.print("\n[bold red]✗ Tests failed - aborting ship[/bold red]")
        raise typer.Exit(1)
    
    console.print("\n[bold green]✓ Tests passed![/bold green]")
    
    # Git push
    console.print("\n[bold]Step 2: Pushing to git[/bold]")
    result = subprocess.run(["git", "push"])
    
    if result.returncode == 0:
        console.print("\n[bold green]✓ Shipped successfully![/bold green]")
    else:
        console.print("\n[bold red]✗ Git push failed[/bold red]")
        raise typer.Exit(1)
