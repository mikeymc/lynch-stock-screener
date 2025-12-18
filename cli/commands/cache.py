"""
Cache commands for bag CLI - Pre-warm stock detail page data
"""
import os
import httpx
import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Cache commands for pre-warming stock detail data")

API_URL = os.getenv("API_URL", "https://lynch-stock-screener.fly.dev")


def get_api_token() -> str:
    """Get API token for production calls"""
    token = os.getenv("API_AUTH_TOKEN")
    if not token:
        console.print("[yellow]API_AUTH_TOKEN not found in environment[/yellow]")
        raise typer.Exit(1)
    return token


def _start_cache_job(job_type: str, display_name: str, limit: int = None, force: bool = False):
    """Helper to start a cache job"""
    token = get_api_token()
    console.print(f"[bold blue]🚀 Starting {display_name} cache job...[/bold blue]")
    
    params = {}
    if limit:
        params["limit"] = limit
    if force:
        params["force_refresh"] = True
    
    payload = {
        "type": job_type,
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
        
        console.print(f"[bold green]✓ {display_name} cache job started![/bold green]")
        console.print(f"[dim]Job ID: {job_id}[/dim]")
        console.print(f"[dim]Monitor: {API_URL}/api/jobs/{job_id}[/dim]")
        return job_id
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to start {display_name} cache:[/bold red] {e}")
        raise typer.Exit(1)


def _stop_cache_job(job_id: int):
    """Helper to stop a cache job"""
    token = get_api_token()
    console.print(f"[bold blue]🛑 Cancelling cache job {job_id}...[/bold blue]")
    
    try:
        response = httpx.post(
            f"{API_URL}/api/jobs/{job_id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0
        )
        response.raise_for_status()
        console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
        raise typer.Exit(1)


# Price History Cache
@app.command("prices")
def prices(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    region: str = typer.Option("us", "--region", "-r", 
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
):
    """Cache weekly price history (yfinance)"""
    
    # Map region to country code (database uses 2-letter codes like 'US', 'CA')
    region_to_country = {
        'us': 'US',
        'north-america': None,  # Would need to query multiple countries: US, CA, MX
        'south-america': None,  # Would need continent-based logic
        'europe': None,  # Would need continent-based logic
        'asia': None,  # Would need continent-based logic
        'all': None  # No filter
    }
    
    if action == "start":
        # Validate region
        valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
        if region not in valid_regions:
            console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
            console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
            raise typer.Exit(1)
        
        # Build params
        params = {}
        if limit:
            params["limit"] = limit
        
        # Add country filter for US region
        country = region_to_country.get(region)
        if country:
            params["country"] = country
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        else:
            headers = {"Content-Type": "application/json"}
        
        console.print(f"[bold blue]🚀 Starting price cache ({region})...[/bold blue]")
        
        payload = {
            "type": "price_history_cache",
            "params": params
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
            
            console.print(f"[bold green]✓ Price cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start price cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        _stop_cache_job(job_id)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# News Cache
@app.command("news")
def news(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
):
    """Cache news articles (Finnhub)"""
    if action == "start":
        _start_cache_job("news_cache", "News", limit=limit)
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        _stop_cache_job(job_id)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# 10-K/10-Q Cache
@app.command("10k")
def ten_k(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh cache"),
):
    """Cache 10-K/10-Q filings (SEC EDGAR)"""
    if action == "start":
        _start_cache_job("10k_cache", "10-K/10-Q", limit=limit, force=force)
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        _stop_cache_job(job_id)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# 8-K Cache
@app.command("8k")
def eight_k(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh cache"),
):
    """Cache 8-K material events (SEC EDGAR)"""
    if action == "start":
        _start_cache_job("8k_cache", "8-K Events", limit=limit, force=force)
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        _stop_cache_job(job_id)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# All caches
@app.command("all")
def all_caches(
    action: str = typer.Argument(..., help="Action: start or stop"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
):
    """Start all 4 cache jobs"""
    if action == "start":
        console.print("[bold blue]🚀 Starting all cache jobs...[/bold blue]")
        _start_cache_job("price_history_cache", "Price History", limit=limit)
        _start_cache_job("news_cache", "News", limit=limit)
        _start_cache_job("10k_cache", "10-K/10-Q", limit=limit)
        _start_cache_job("8k_cache", "8-K Events", limit=limit)
        console.print("[bold green]✓ All cache jobs started![/bold green]")
    else:
        console.print("[yellow]Use individual commands to stop specific jobs[/yellow]")
        console.print("[dim]Example: bag cache prices stop <job_id>[/dim]")
