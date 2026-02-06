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


def get_api_url(prod: bool = False) -> str:
    """Get the API base URL based on environment and target"""
    if prod:
        return API_URL
    port = os.getenv("PORT", "5001")
    return f"http://localhost:{port}"


def get_api_token(optional: bool = False) -> str:
    """Get API token from environment"""
    token = os.getenv("API_AUTH_TOKEN")
    if not token and not optional:
        console.print("[yellow]API_AUTH_TOKEN not found in environment[/yellow]")
        raise typer.Exit(1)
    return token


def get_headers(is_local: bool = True) -> dict:
    """Get headers for API calls, including Bearer token"""
    # Token is optional locally if bypass is on
    token = get_api_token(optional=is_local)
    
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _start_cache_job(job_type: str, display_name: str, limit: int = None, force: bool = False, prod: bool = False):
    """Helper to start a cache job"""
    api_url = get_api_url(prod)
    headers = get_headers(is_local=not prod)
    
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
            f"{api_url}/api/jobs",
            json=payload,
            headers=headers,
            timeout=30.0
        )
        response.raise_for_status()
        
        data = response.json()
        job_id = data.get("job_id")
        
        console.print(f"[bold green]✓ {display_name} cache job started![/bold green]")
        console.print(f"[dim]Job ID: {job_id}[/dim]")
        console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
        return job_id
        
    except httpx.HTTPError as e:
        console.print(f"[bold red]✗ Failed to start {display_name} cache:[/bold red] {e}")
        raise typer.Exit(1)


def _stop_cache_job(job_id: int, prod: bool = False):
    """Helper to stop a cache job"""
    api_url = get_api_url(prod)
    headers = get_headers(is_local=not prod)
    
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
        raise typer.Exit(1)


# Price History Cache (renamed from prices to avoid confusion)
@app.command("history")
def history(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    region: str = typer.Option("us", "--region", "-r", 
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh (bypass weekly cache check)"),
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
        if force:
            params["force_refresh"] = True
        
        # Pass region directly (worker will use TradingView regions)
        params["region"] = region
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
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
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
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


# Fast Price Update (TradingView Scanner)
@app.command("prices")
def prices(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    region: str = typer.Option("us", "--region", "-r", 
                               help="Region: us, europe, asia, all (defaults to us for speed)"),
):
    """Fast price update via TradingView (15-min interval)"""
    if action == "start":
        # Build params
        # Support comma-separated regions if passed manually (e.g. "us,europe")
        params = {"regions": region.split(',')}

        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        console.print(f"[bold blue]🚀 Starting fast price update ({region})...[/bold blue]")
        
        payload = {
            "type": "price_update",
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
            
            console.print(f"[bold green]✓ Price update job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start price update:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        # ... logic for stop (reuse helper if possible or duplicate)
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        api_url = API_URL if prod else "http://localhost:5001"
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        console.print(f"[bold blue]🛑 Cancelling price update job {job_id}...[/bold blue]")
        
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


# News Cache
@app.command("news")
def news(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
):
    """Cache news articles (Finnhub)"""
    if action == "start":
        # Build params
        params = {}
        if limit:
            params["limit"] = limit
        if symbols:
            # Convert comma-separated string to list
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")

        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"

        # Get token if prod
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

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
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
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
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh cache"),
    use_rss: bool = typer.Option(True, "--use-rss/--no-rss", help="Use RSS feed to pre-filter stocks with new filings"),
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
        params = {"region": region, "use_rss": use_rss}
        if limit:
            params["limit"] = limit
        if symbols:
            # Convert comma-separated string to list
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")
        if force:
            params["force_refresh"] = True
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
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
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
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
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh cache"),
    use_rss: bool = typer.Option(True, "--use-rss/--no-rss", help="Use RSS feed to pre-filter stocks with new filings"),
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
        params = {"region": region, "use_rss": use_rss}
        if limit:
            params["limit"] = limit
        if symbols:
            # Convert comma-separated string to list
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")
        if force:
            params["force_refresh"] = True
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
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
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
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


# Outlook Cache (forward metrics + insider trades)
@app.command("outlook")
def outlook(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
):
    """Cache future outlook data: forward P/E, PEG, EPS, analyst targets, and insider trades (yfinance)"""
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
        if symbols:
            # Convert comma-separated string to list
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
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
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
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
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh (bypass cache check)"),
    use_rss: bool = typer.Option(True, "--use-rss/--no-rss", help="Use RSS feed to pre-filter stocks with new filings"),
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
        params = {"region": region, "use_rss": use_rss}
        if limit:
            params["limit"] = limit
        if force:
            params["force_refresh"] = True
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token if prod
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
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
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
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
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
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
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
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


# Forward Metrics Cache
@app.command("forward_metrics")
def forward_metrics(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
):
    """Cache forward metrics: forward PE/EPS/PEG, analyst estimates, EPS trends, revisions, recommendations (yfinance)"""
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
        if symbols:
            # Convert comma-separated string to list
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token (always required)
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        console.print(f"[bold blue]🚀 Starting forward metrics cache ({region})...[/bold blue]")
        console.print("[dim]Caching: forward PE/EPS/PEG, analyst estimates, EPS trends, revisions, recommendations[/dim]")
        
        payload = {
            "type": "forward_metrics_cache",
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
            
            console.print(f"[bold green]✓ Forward metrics cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start forward metrics cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL (same as start)
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token (always required)
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        console.print(f"[bold blue]🛑 Cancelling forward metrics cache job {job_id}...[/bold blue]")
        
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
    """Start all 7 cache jobs"""
    if action == "start":
        console.print("[bold blue]🚀 Starting all cache jobs...[/bold blue]")
        _start_cache_job("price_history_cache", "Price History", limit=limit)
        _start_cache_job("news_cache", "News", limit=limit)
        _start_cache_job("10k_cache", "10-K/10-Q", limit=limit)
        _start_cache_job("8k_cache", "8-K Events", limit=limit)
        _start_cache_job("form4_cache", "Form 4 (Insiders)", limit=limit)
        _start_cache_job("outlook_cache", "Outlook (Forward Metrics + Insiders)", limit=limit)
        _start_cache_job("forward_metrics_cache", "Forward Metrics (Estimates)", limit=limit)
        console.print("[bold green]✓ All cache jobs started![/bold green]")
    else:
        console.print("[yellow]Use individual commands to stop specific jobs[/yellow]")
        console.print("[dim]Example: bag cache prices stop <job_id>[/dim]")

# Historical Fundamentals Cache (Cold Storage - runs quarterly)
@app.command("historical")
def historical(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh (re-fetch even if historical data exists)"),
):
    """Cache historical fundamentals >2 years old via company_facts API (runs quarterly)"""
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
        if symbols:
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")
        if force:
            params["force_refresh"] = True

        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"

        # Get token
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        console.print(f"[bold blue]🚀 Starting historical fundamentals cache ({region})...[/bold blue]")
        console.print("[dim]Caching: >2 year annual data via company_facts API[/dim]")

        payload = {
            "type": "historical_fundamentals_cache",
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

            console.print(f"[bold green]✓ Historical fundamentals cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id

        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start historical cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)

    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)

        api_url = API_URL if prod else "http://localhost:5001"
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}

        console.print(f"[bold blue]🛑 Cancelling historical cache job {job_id}...[/bold blue]")

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


# Quarterly Fundamentals Cache (Hot Data - runs nightly with smart caching)
@app.command("quarterly")
def quarterly(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    region: str = typer.Option("us", "--region", "-r",
                               help="Region to cache: us, north-america, south-america, europe, asia, all"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh (re-fetch even if quarterly data is current)"),
):
    """Cache recent quarterly data (last 8 quarters) via 10-Q parsing with smart caching (runs nightly)"""
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
        if symbols:
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")
        if force:
            params["force_refresh"] = True

        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"

        # Get token
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        console.print(f"[bold blue]🚀 Starting quarterly fundamentals cache ({region})...[/bold blue]")
        console.print("[dim]Caching: last 8 quarters via 10-Q parsing (smart cache: only new quarters)[/dim]")

        payload = {
            "type": "quarterly_fundamentals_cache",
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

            console.print(f"[bold green]✓ Quarterly fundamentals cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id

        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start quarterly cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)

    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)

        api_url = API_URL if prod else "http://localhost:5001"
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}

        console.print(f"[bold blue]🛑 Cancelling quarterly cache job {job_id}...[/bold blue]")

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


# Thesis Caching (Generate Analysis)
@app.command("theses")
def theses(
    action: str = typer.Argument(..., help="Action: start or stop"),
    job_id: int = typer.Argument(None, help="Job ID (required for stop)"),
    prod: bool = typer.Option(False, "--prod", help="Trigger production API instead of local"),
    limit: int = typer.Option(None, "--limit", "-l", help="Limit number of stocks (default: unlimited)"),
    symbols: str = typer.Option(None, "--symbols", "-s", help="Comma-separated symbols to process (for testing)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh (ignore max_age)"),
):
    """Cache investment theses (generate/refresh AI analysis)"""
    if action == "start":
        # Build params
        params = {}
        if limit:
            params["limit"] = limit
        if symbols:
            # Convert comma-separated string to list
            params["symbols"] = [s.strip().upper() for s in symbols.split(",")]
            console.print(f"[dim]Processing specific symbols: {params['symbols']}[/dim]")
        if force:
            params["force_refresh"] = True
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        console.print(f"[bold blue]🚀 Starting thesis cache/refresh...[/bold blue]")
        
        payload = {
            "type": "thesis_refresher",
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
            
            console.print(f"[bold green]✓ Thesis cache job started![/bold green]")
            console.print(f"[dim]Job ID: {job_id}[/dim]")
            console.print(f"[dim]Monitor: {api_url}/api/jobs/{job_id}[/dim]")
            return job_id
            
        except httpx.HTTPError as e:
            console.print(f"[bold red]✗ Failed to start thesis cache:[/bold red] {e}")
            if not prod:
                console.print("[yellow]Make sure local server is running[/yellow]")
            raise typer.Exit(1)
            
    elif action == "stop":
        if not job_id:
            console.print("[bold red]✗ Job ID required for stop[/bold red]")
            raise typer.Exit(1)
        
        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"
        
        # Get token
        token = get_api_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        console.print(f"[bold blue]🛑 Cancelling thesis cache job {job_id}...[/bold blue]")
        
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
