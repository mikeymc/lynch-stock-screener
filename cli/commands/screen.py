"""
Stock screening commands for bag CLI
"""
import os
import httpx
import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Stock screening commands")

API_URL = os.getenv("API_URL", "https://lynch-stock-screener.fly.dev")
LOCAL_URL = "http://localhost:5001"


def get_api_token() -> str:
    """Get API token for production calls"""
    token = os.getenv("API_AUTH_TOKEN")
    if not token:
        console.print("[yellow]API_AUTH_TOKEN not found in environment[/yellow]")
        console.print("[yellow]This is required for --prod flag[/yellow]")
        console.print("\n[cyan]Token is already in .env file - make sure .env exists[/cyan]")
        raise typer.Exit(1)
    return token


@app.command()
def start(
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    algorithm: str = typer.Option("weighted", "--algorithm", "-a", help="Screening algorithm to use"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks to screen"),
    region: str = typer.Option("us", "--region", "-r", 
                               help="Region to screen: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh all cached data (bypasses cache)"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to screen (for testing)"),
):
    """Start stock screening"""
    
    # Validate region
    valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
    if region not in valid_regions:
        console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
        console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
        raise typer.Exit(1)
    
    # Parse symbols if provided
    symbol_list = None
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(',')]
        console.print(f"[dim]Screening specific symbols: {symbol_list}[/dim]")
    
    # Get API token (required for both local and prod now)
    token = get_api_token()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    if prod:
        # Production: Call /api/jobs
        console.print(f"[bold blue]🚀 Triggering production screening ({region})...[/bold blue]")
        api_url = API_URL
    else:
        # Local: Call /api/jobs
        console.print(f"[bold blue]🚀 Starting local screening ({region})...[/bold blue]")
        api_url = LOCAL_URL
        
    payload = {
        "type": "full_screening",
        "params": {"algorithm": algorithm, "region": region, "force_refresh": force}
    }
    if limit:
        payload["params"]["limit"] = limit
    if symbol_list:
        payload["params"]["symbols"] = symbol_list
    
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
        # Local might verify session_id if it returns one, but jobs API returns job_id
        
        console.print(f"[bold green]✓ Screening job triggered![/bold green]")
        console.print(f"[dim]Job ID: {job_id}[/dim]")
        console.print(f"[dim]Monitor at: {api_url}/api/jobs/{job_id}[/dim]")
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to trigger screening:[/bold red] {e}")
        if not prod:
            console.print("[yellow]Make sure local server is running (npm run dev) and API_AUTH_TOKEN is correct[/yellow]")
        raise typer.Exit(1)


@app.command()
def stop(
    session_id: int = typer.Argument(..., help="Session ID or Job ID to stop"),
    prod: bool = typer.Option(False, "--prod", help="Cancel production job instead of local session"),
):
    """Stop screening session"""
    
    # Get API token (required for both local and prod now)
    token = get_api_token()
    headers = {"Authorization": f"Bearer {token}"}

    if prod:
        # Production: Cancel job via /api/jobs/<id>/cancel
        console.print(f"[bold blue]🛑 Cancelling production job {session_id}...[/bold blue]")
        url = f"{API_URL}/api/jobs/{session_id}/cancel"
        
        try:
            response = httpx.post(
                url,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            
            console.print(f"[bold green]✓ Job cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            raise typer.Exit(1)
    else:
        # Local: Stop session via /api/screen/stop/<id> (auth header added for consistency)
        console.print(f"[bold blue]🛑 Stopping local session {session_id}...[/bold blue]")
        url = f"{LOCAL_URL}/api/screen/stop/{session_id}"
        
        try:
            response = httpx.post(
                url,
                headers=headers,  # Include token even if currently optional
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            console.print(f"[bold green]✓ Session stopped![/bold green]")
            console.print(f"[dim]{data.get('message', '')}[/dim]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to stop session:[/bold red] {e}")
            console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
