"""
GitHub Actions job trigger commands for bag CLI
"""
import os
import subprocess
import typer
import httpx
from rich.console import Console
from rich.prompt import Prompt

console = Console()
app = typer.Typer(help="Trigger background jobs via API")

API_URL = os.getenv("API_URL", "https://lynch-stock-screener.fly.dev")


def get_api_token() -> str:
    """Get API token from environment or fly secrets"""
    token = os.getenv("API_AUTH_TOKEN")
    if not token:
        console.print("[yellow]API_AUTH_TOKEN not found in environment[/yellow]")
        console.print("[yellow]This is the same token used by GitHub Actions to authenticate with /api/jobs[/yellow]")
        console.print("\n[cyan]To get the token:[/cyan]")
        console.print("  1. fly secrets list")
        console.print("  2. export API_AUTH_TOKEN=<value_from_secrets>")
        console.print("\n[dim]Or set API_URL to use localhost for testing:[/dim]")
        console.print("  export API_URL=http://localhost:5000")
        raise typer.Exit(1)
    return token


def trigger_job(job_type: str, params: dict = None):
    """Trigger a job via the API"""
    token = get_api_token()
    
    payload = {
        "type": job_type,
        "params": params or {}
    }
    
    console.print(f"[bold blue]🚀 Triggering {job_type} job...[/bold blue]")
    
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
        
        console.print(f"[bold green]✓ Job triggered successfully![/bold green]")
        console.print(f"[dim]Job ID: {job_id}[/dim]")
        console.print(f"[dim]Monitor at: {API_URL}/api/jobs/{job_id}[/dim]")
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to trigger job:[/bold red] {e}")
        raise typer.Exit(1)


@app.command()
def screen(
    algorithm: str = typer.Option("weighted", "--algorithm", "-a", help="Screening algorithm to use")
):
    """Trigger full stock screening"""
    trigger_job("full_screening", {"algorithm": algorithm})


@app.command()
def sec_cache(
    limit: int = typer.Option(None, "--limit", "-l", help="Process only first N stocks"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh, bypass cache"),
):
    """Trigger SEC filings cache refresh"""
    params = {}
    if limit:
        params["limit"] = limit
    if force:
        params["force_refresh"] = True
    
    trigger_job("sec_filings_cache", params)


@app.command()
def sec_refresh():
    """Trigger SEC data refresh (alias for sec-cache)"""
    console.print("[dim]Note: This is an alias for 'bag jobs sec-cache'[/dim]")
    trigger_job("sec_refresh", {})

