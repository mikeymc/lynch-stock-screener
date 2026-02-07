# ABOUTME: Shared helper functions for cache CLI commands.
# ABOUTME: Provides API URL/token resolution, headers, and job start/stop utilities.
import os
import httpx
import typer
from rich.console import Console

console = Console()

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
