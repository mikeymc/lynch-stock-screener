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
):
    """Start stock screening"""
    
    # Validate region
    valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
    if region not in valid_regions:
        console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
        console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
        raise typer.Exit(1)
    
    if prod:
        # Production: Call /api/jobs
        token = get_api_token()
        console.print(f"[bold blue]🚀 Triggering production screening ({region})...[/bold blue]")
        
        payload = {
            "type": "full_screening",
            "params": {"algorithm": algorithm, "region": region}
        }
        if limit:
            payload["params"]["limit"] = limit
        
        try:
            response = httpx.post(
                f"{API_URL}/api/jobs",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                },
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            job_id = data.get("job_id")
            
            console.print(f"[bold green]✓ Screening job triggered![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor at: {API_URL}/api/jobs/{job_id}[/dim]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to trigger screening:[/bold red] {e}")
            raise typer.Exit(1)
    else:
        # Local: Call /api/screen/start
        console.print(f"[bold blue]🚀 Starting local screening ({region})...[/bold blue]")
        
        payload = {
            "algorithm": algorithm,
            "force_refresh": False,
            "region": region
        }
        if limit:
            payload["limit"] = limit
        
        try:
            response = httpx.post(
                f"{LOCAL_URL}/api/screen/start",
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            
            data = response.json()
            session_id = data.get("session_id")
            
            console.print(f"[bold green]✓ Screening started![/bold green]")
            console.print(f"[dim]Session ID: {session_id}[/dim]")
            console.print(f"[dim]Monitor at: {LOCAL_URL}/api/screen/progress/{session_id}[/dim]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start screening:[/bold red] {e}")
            console.print("[yellow]Make sure local server is running (npm run dev)[/yellow]")
            raise typer.Exit(1)


@app.command()
def stop(
    session_id: int = typer.Argument(..., help="Session ID or Job ID to stop"),
    prod: bool = typer.Option(False, "--prod", help="Cancel production job instead of local session"),
):
    """Stop screening session"""
    
    if prod:
        # Production: Cancel job via /api/jobs/<id>/cancel
        token = get_api_token()
        console.print(f"[bold blue]🛑 Cancelling production job {session_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{API_URL}/api/jobs/{session_id}/cancel",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0
            )
            response.raise_for_status()
            
            console.print(f"[bold green]✓ Job cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            raise typer.Exit(1)
    else:
        # Local: Stop session via /api/screen/stop/<id>
        console.print(f"[bold blue]🛑 Stopping local session {session_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{LOCAL_URL}/api/screen/stop/{session_id}",
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
