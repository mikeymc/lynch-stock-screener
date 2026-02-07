# ABOUTME: Cache commands for content data (news, outlook, transcripts, forward_metrics, theses).
# ABOUTME: Each command triggers a background job via the API to cache content-related stock data.
import httpx
import typer

from cli.commands.cache import app
from cli.commands.cache.helpers import console, API_URL, get_api_token


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
