# ABOUTME: Cache commands for price and fundamental data (history, prices, historical, quarterly).
# ABOUTME: Each command triggers a background job via the API to cache stock data.
import httpx
import typer

from cli.commands.cache import app
from cli.commands.cache.helpers import console, API_URL, get_api_token


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
    use_rss: bool = typer.Option(True, "--use-rss/--no-rss", help="Use RSS feed to pre-filter stocks with new filings"),
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
        if use_rss:
            params["use_rss"] = True

        # Determine API URL
        api_url = API_URL if prod else "http://localhost:5001"

        # Get token
        token = get_api_token()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        console.print(f"[bold blue]🚀 Starting quarterly fundamentals cache ({region})...[/bold blue]")
        console.print(f"[dim]Caching: last 8 quarters via 10-K/10-Q parsing (smart cache: only new quarters, RSS={use_rss})[/dim]")

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
