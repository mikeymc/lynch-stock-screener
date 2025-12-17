"""
SEC cache commands for bag CLI
"""
import os
import httpx
import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="SEC filings cache commands")

API_URL = os.getenv("API_URL", "https://lynch-stock-screener.fly.dev")
LOCAL_URL = "http://localhost:5000"


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
    limit: int = typer.Option(None, "--limit", "-l", help="Process only first N stocks"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh, bypass cache"),
):
    """Start SEC filings cache refresh"""
    
    params = {}
    if limit:
        params["limit"] = limit
    if force:
        params["force_refresh"] = True
    
    if prod:
        # Production: Call /api/jobs
        token = get_api_token()
        console.print(f"[bold blue]🚀 Triggering production SEC cache refresh...[/bold blue]")
        
        payload = {
            "type": "sec_filings_cache",
            "params": params
        }
        
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
            
            console.print(f"[bold green]✓ SEC cache job triggered![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor at: {API_URL}/api/jobs/{job_id}[/dim]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to trigger SEC cache:[/bold red] {e}")
            raise typer.Exit(1)
    else:
        # Local: Direct call (no local endpoint exists yet, so inform user)
        console.print("[yellow]Local SEC cache refresh not implemented yet[/yellow]")
        console.print("[cyan]For now, use --prod flag to trigger production job[/cyan]")
        console.print(f"\n[dim]Example: bag sec-cache start --prod --limit 100[/dim]")
        raise typer.Exit(1)


@app.command()
def stop(
    job_id: int = typer.Argument(..., help="Job ID to stop"),
    prod: bool = typer.Option(False, "--prod", help="Cancel production job"),
):
    """Stop SEC cache job"""
    
    if prod:
        # Production: Cancel job via /api/jobs/<id>/cancel
        token = get_api_token()
        console.print(f"[bold blue]🛑 Cancelling production SEC cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{API_URL}/api/jobs/{job_id}/cancel",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0
            )
            response.raise_for_status()
            
            console.print(f"[bold green]✓ Job cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            raise typer.Exit(1)
    else:
        console.print("[yellow]Local SEC cache stop not implemented yet[/yellow]")
        console.print("[cyan]Use --prod flag to cancel production job[/cyan]")
        raise typer.Exit(1)
