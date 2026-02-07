# ABOUTME: Cache commands for SEC filing data (10-K, 8-K, Form 4) and the all-caches command.
# ABOUTME: Each command triggers a background job via the API to cache filing-related stock data.
import httpx
import typer

from cli.commands.cache import app
from cli.commands.cache.helpers import console, API_URL, get_api_token, _start_cache_job


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
