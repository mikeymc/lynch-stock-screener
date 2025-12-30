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
        
        # Pass region directly (worker will use TradingView regions)
        params["region"] = region
        
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
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {"Authorization": f"Bearer {token}"}
        else:
            headers = {}
        
        console.print(f"[bold blue]🛑 Cancelling cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{api_url}/api/jobs/{job_id}/cancel",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# Clear Price Cache
@app.command("clear-prices")
def clear_prices(
    symbol: str = typer.Argument(None, help="Symbol to clear, or omit for ALL symbols"),
    prod: bool = typer.Option(False, "--prod", help="Use production database"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Clear weekly price cache (use after fixing split adjustment)"""
    if symbol:
        console.print(f"[yellow]⚠ This will delete all cached weekly prices for {symbol}[/yellow]")
    else:
        console.print("[bold red]⚠ This will delete ALL cached weekly prices for ALL symbols![/bold red]")
    
    if not confirm:
        confirmed = typer.confirm("Are you sure you want to continue?")
        if not confirmed:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)
    
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
    
    console.print(f"[bold blue]🗑️ Clearing price cache on {'production' if prod else 'local'}...[/bold blue]")
    
    try:
        payload = {"symbol": symbol} if symbol else {}
        
        response = httpx.post(
            f"{api_url}/api/admin/clear-weekly-prices",
            json=payload,
            headers=headers,
            timeout=60.0
        )
        response.raise_for_status()
        
        data = response.json()
        rows_deleted = data.get("rows_deleted", 0)
        
        if symbol:
            console.print(f"[bold green]✓ Deleted {rows_deleted} weekly price records for {symbol}[/bold green]")
        else:
            console.print(f"[bold green]✓ Cleared all weekly prices ({rows_deleted} affected)[/bold green]")
        
        console.print("[dim]Run 'bag cache prices start --prod' to re-fetch split-adjusted prices[/dim]")
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to clear prices:[/bold red] {e}")
        if not prod:
            console.print("[yellow]Make sure local server is running[/yellow]")
        raise typer.Exit(1)


# News Cache
@app.command("news")
def news(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
):
    """Cache news articles (Finnhub)"""
    if action == "start":
        # Build params
        params = {}
        if limit:
            params["limit"] = limit
        
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
        
        console.print(f"[bold blue]🚀 Starting news cache...[/bold blue]")
        
        payload = {
            "type": "news_cache",
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
            
            console.print(f"[bold green]✓ News cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start news cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {"Authorization": f"Bearer {token}"}
        else:
            headers = {}
        
        console.print(f"[bold blue]🛑 Cancelling news cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{api_url}/api/jobs/{job_id}/cancel",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# 10-K/10-Q Cache
@app.command("10k")
def ten_k(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh cache"),
):
    """Cache 10-K/10-Q filings (SEC EDGAR)"""
    if action == "start":
        # Validate region
        valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
        if region not in valid_regions:
            console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
            console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
            raise typer.Exit(1)
        
        # Build params
        params = {"region": region}
        if limit:
            params["limit"] = limit
        if force:
            params["force_refresh"] = True
        
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
        
        console.print(f"[bold blue]🚀 Starting 10-K/10-Q cache ({region})...[/bold blue]")
        
        payload = {
            "type": "10k_cache",
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
            
            console.print(f"[bold green]✓ 10-K/10-Q cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start 10-K/10-Q cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {"Authorization": f"Bearer {token}"}
        else:
            headers = {}
        
        console.print(f"[bold blue]🛑 Cancelling 10-K/10-Q cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{api_url}/api/jobs/{job_id}/cancel",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# 8-K Cache
@app.command("8k")
def eight_k(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh cache"),
):
    """Cache 8-K material events (SEC EDGAR)"""
    if action == "start":
        # Validate region
        valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
        if region not in valid_regions:
            console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
            console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
            raise typer.Exit(1)
        
        # Build params
        params = {"region": region}
        if limit:
            params["limit"] = limit
        if force:
            params["force_refresh"] = True
        
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
        
        console.print(f"[bold blue]🚀 Starting 8-K cache ({region})...[/bold blue]")
        
        payload = {
            "type": "8k_cache",
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
            
            console.print(f"[bold green]✓ 8-K cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start 8-K cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {"Authorization": f"Bearer {token}"}
        else:
            headers = {}
        
        console.print(f"[bold blue]🛑 Cancelling 8-K cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{api_url}/api/jobs/{job_id}/cancel",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# Clear 8-K Cache
@app.command("clear-8k")
def clear_8k(
    symbol: str = typer.Argument(None, help="Symbol to clear, or omit for ALL symbols"),
    prod: bool = typer.Option(False, "--prod", help="Use production database"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Clear 8-K material events cache (use after updating EX-99 extraction)"""
    if symbol:
        console.print(f"[yellow]⚠ This will delete all cached 8-K events for {symbol}[/yellow]")
    else:
        console.print("[bold red]⚠ This will delete ALL cached 8-K material events for ALL symbols![/bold red]")
    
    if not confirm:
        confirmed = typer.confirm("Are you sure you want to continue?")
        if not confirmed:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)
    
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
    
    console.print(f"[bold blue]🗑️ Clearing 8-K cache on {'production' if prod else 'local'}...[/bold blue]")
    
    try:
        payload = {"symbol": symbol} if symbol else {}
        
        response = httpx.post(
            f"{api_url}/api/admin/clear-material-events",
            json=payload,
            headers=headers,
            timeout=60.0
        )
        response.raise_for_status()
        
        data = response.json()
        rows_deleted = data.get("rows_deleted", 0)
        
        if symbol:
            console.print(f"[bold green]✓ Deleted {rows_deleted} 8-K events for {symbol}[/bold green]")
        else:
            console.print(f"[bold green]✓ Cleared all 8-K material events ({rows_deleted} affected)[/bold green]")
        
        console.print("[dim]Run 'bag cache 8k start --prod' to re-fetch with EX-99 exhibit content[/dim]")
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to clear 8-K cache:[/bold red] {e}")
        if not prod:
            console.print("[yellow]Make sure local server is running[/yellow]")
        raise typer.Exit(1)


# Outlook Cache (forward metrics + insider trades)
@app.command("outlook")
def outlook(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
):
    """Cache future outlook data: forward P/E, PEG, EPS, and insider trades (yfinance)"""
    if action == "start":
        # Validate region
        valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
        if region not in valid_regions:
            console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
            console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
            raise typer.Exit(1)
        
        # Build params
        params = {"region": region}
        if limit:
            params["limit"] = limit
        
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
        
        console.print(f"[bold blue]🚀 Starting outlook cache ({region})...[/bold blue]")
        console.print("[dim]Caching: forward P/E, forward PEG, forward EPS, insider trades[/dim]")
        
        payload = {
            "type": "outlook_cache",
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
            
            console.print(f"[bold green]✓ Outlook cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start outlook cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {"Authorization": f"Bearer {token}"}
        else:
            headers = {}
        
        console.print(f"[bold blue]🛑 Cancelling outlook cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{api_url}/api/jobs/{job_id}/cancel",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# Form 4 Cache
@app.command("form4")
def form4(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
):
    """Cache SEC Form 4 filings (Insider Transactions)"""
    if action == "start":
        # Validate region
        valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
        if region not in valid_regions:
            console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
            console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
            raise typer.Exit(1)
        
        # Build params
        params = {"region": region}
        if limit:
            params["limit"] = limit
        
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
        
        console.print(f"[bold blue]🚀 Starting Form 4 cache ({region})...[/bold blue]")
        
        payload = {
            "type": "form4_cache",
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
            
            console.print(f"[bold green]✓ Form 4 cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start Form 4 cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {"Authorization": f"Bearer {token}"}
        else:
            headers = {}
        
        console.print(f"[bold blue]🛑 Cancelling Form 4 cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{api_url}/api/jobs/{job_id}/cancel",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# Transcripts Cache
@app.command("transcripts")
def transcripts(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh (re-fetch even if cached)"),
):
    """Cache earnings call transcripts (MarketBeat scraping)"""
    if action == "start":
        # Validate region
        valid_regions = ['us', 'north-america', 'south-america', 'europe', 'asia', 'all']
        if region not in valid_regions:
            console.print(f"[bold red]✗ Invalid region: {region}[/bold red]")
            console.print(f"[yellow]Valid regions: {', '.join(valid_regions)}[/yellow]")
            raise typer.Exit(1)
        
        # Build params
        params = {"region": region}
        if limit:
            params["limit"] = limit
        if force:
            params["force_refresh"] = True
        if symbols:
            # Convert comma-separated string to list
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Testing specific symbols: {params['symbols']}[/dim]")
        
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
        
        console.print(f"[bold blue]🚀 Starting transcript cache ({region})...[/bold blue]")
        
        payload = {
            "type": "transcript_cache",
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
            
            console.print(f"[bold green]✓ Transcript cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start transcript cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        if prod:
            token = get_api_token()
            headers = {"Authorization": f"Bearer {token}"}
        else:
            headers = {}
        
        console.print(f"[bold blue]🛑 Cancelling transcript cache job {job_id}...[/bold blue]")
        
        try:
            response = httpx.post(
                f"{api_url}/api/jobs/{job_id}/cancel",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            console.print(f"[bold green]✓ Job {job_id} cancelled![/bold green]")
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to cancel job:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(f"[bold red]✗ Unknown action: {action}[/bold red]")
        raise typer.Exit(1)


# All caches
@app.command("all")
def all_caches(
    action: str = typer.Argument(..., help="Action: start or stop"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
):
    """Start all 5 cache jobs"""
    if action == "start":
        console.print("[bold blue]🚀 Starting all cache jobs...[/bold blue]")
        _start_cache_job("price_history_cache", "Price History", limit=limit)
        _start_cache_job("news_cache", "News", limit=limit)
        _start_cache_job("10k_cache", "10-K/10-Q", limit=limit)
        _start_cache_job("8k_cache", "8-K Events", limit=limit)
        _start_cache_job("form4_cache", "Form 4 (Insiders)", limit=limit)
        _start_cache_job("outlook_cache", "Outlook (Forward Metrics + Insiders)", limit=limit)
        console.print("[bold green]✓ All cache jobs started![/bold green]")
    else:
        console.print("[yellow]Use individual commands to stop specific jobs[/yellow]")
        console.print("[dim]Example: bag cache prices stop <job_id>[/dim]")

