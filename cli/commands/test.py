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
    skip_e2e: bool = typer.Option(False, "--skip-e2e", help="Skip e2e tests"),
):
    """Run pytest tests (backend, CLI, and e2e)"""
    cmd = ["uv", "run", "pytest"]

    if file:
        cmd.append(file)
    else:
        # Run all test suites by default
        test_dirs = [
            str(TESTS_DIR / "backend"),
            str(TESTS_DIR / "cli"),
        ]
        if not skip_e2e:
            test_dirs.append(str(TESTS_DIR / "e2e"))

        cmd.extend(test_dirs)

    cmd.extend(["-v", "--tb=short"])

    if match:
        cmd.extend(["-k", match])

    console.print(f"[bold blue]🧪 Running tests...[/bold blue]")
    console.print(f"[dim]Command: {' '.join(cmd)}[/dim]\n")

    result = subprocess.run(cmd)

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
