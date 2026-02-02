"""
Strategy commands for bag CLI
"""
import os
import httpx
import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Strategy management commands")

API_URL = os.getenv("API_URL", "https://lynch-stock-screener.fly.dev")
LOCAL_URL = "http://localhost:5001"


def get_api_token() -> str:
    """Get API token for production calls"""
    token = os.getenv("API_AUTH_TOKEN")
    if not token:
        console.print("[yellow]API_AUTH_TOKEN not found in environment[/yellow]")
        console.print("[yellow]This is required for authentication[/yellow]")
        raise typer.Exit(1)
    return token


@app.command()
def run(
    strategy_id: int = typer.Argument(..., help="ID of the strategy to run"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks to process"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
):
    """Run a specific strategy manually"""
    
    # Get API token (required for both local and prod)
    token = get_api_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    if prod:
        console.print(f"[bold blue]🚀 Triggering production strategy run for ID {strategy_id}...[/bold blue]")
        api_url = API_URL
    else:
        console.print(f"[bold blue]🚀 Starting local strategy run for ID {strategy_id}...[/bold blue]")
        api_url = LOCAL_URL
        
    payload = {
        "type": "strategy_execution",
        "params": {
            "strategy_ids": [strategy_id],
            "limit": limit
        }
    }
    
    try:
        response = httpx.post(
            f"{api_url}/api/jobs",
            json=payload,
            headers=headers,
            timeout=30.0
        )
        response.raise_for_status()
        
        data = response.json()
        job_id = data.get("job_id")
        
        console.print(f"[bold green]✓ Strategy execution job triggered![/bold green]")
        console.print(f"[dim]Job ID: {job_id}[/dim]")
        if prod:
            console.print(f"[dim]Monitor at: {api_url}/api/jobs/{job_id}[/dim]")
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to trigger strategy run:[/bold red] {e}")
        if not prod:
            console.print("[yellow]Make sure local server is running (npm run dev) and API_AUTH_TOKEN is correct[/yellow]")
        raise typer.Exit(1)
