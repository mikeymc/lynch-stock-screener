"""
Production environment commands for bag CLI
"""
import typer
from rich.console import Console
from cli.utils.fly import run_fly_command, get_machines, filter_machines, select_machine_interactive

console = Console()
app = typer.Typer(help="Production environment operations")


@app.command()
def deploy():
    """Deploy to Fly.io"""
    console.print("[bold blue]🚀 Deploying to Fly.io...[/bold blue]")
    run_fly_command(["deploy"])
    console.print("[bold green]✓ Deployment complete![/bold green]")


@app.command()
def machines():
    """List Fly.io machines"""
    run_fly_command(["machines", "list"])


@app.command()
def restart(
    web: bool = typer.Option(False, "--web", help="Restart web machine"),
    worker: bool = typer.Option(False, "--worker", help="Restart worker machine"),
    all: bool = typer.Option(False, "--all", help="Restart all machines"),
):
    """Restart Fly.io machines"""
    machines_list = get_machines()
    
    if not machines_list:
        console.print("[red]No machines found[/red]")
        raise typer.Exit(1)
    
    # Determine which machines to restart
    if all:
        targets = machines_list
    elif worker:
        targets = filter_machines(machines_list, "worker")
    elif web:
        targets = filter_machines(machines_list, "web")
    else:
        # Default: restart web machine
        targets = filter_machines(machines_list, "web")
    
    if not targets:
        console.print("[yellow]No matching machines found[/yellow]")
        raise typer.Exit(1)
    
    # Restart each target
    for machine in targets:
        machine_id = machine["id"]
        name = machine.get("name", "unknown")
        console.print(f"[blue]Restarting {name} ({machine_id[:12]}...)...[/blue]")
        run_fly_command(["machine", "restart", machine_id])
    
    console.print("[bold green]✓ Restart complete![/bold green]")


@app.command()
def logs(
    tail: bool = typer.Option(False, "--tail", "-t", help="Stream logs (tail)"),
    hours: int = typer.Option(None, "--hours", "-h", help="Show logs from last N hours"),
):
    """View Fly.io logs"""
    if tail:
        console.print("[bold blue]📋 Streaming logs (Ctrl+C to stop)...[/bold blue]")
        try:
            run_fly_command(["logs"])
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped streaming logs[/yellow]")
    elif hours is not None:
        console.print(f"[bold blue]📋 Showing logs from last {hours} hours...[/bold blue]")
        run_fly_command(["logs", "--hours", str(hours)])
    else:
        # Default: tail
        console.print("[bold blue]📋 Streaming logs (Ctrl+C to stop)...[/bold blue]")
        try:
            run_fly_command(["logs"])
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped streaming logs[/yellow]")


@app.command()
def ssh(
    web: bool = typer.Option(False, "--web", help="SSH into web machine"),
    worker: bool = typer.Option(False, "--worker", help="SSH into worker machine"),
):
    """SSH into a Fly.io machine"""
    machines_list = get_machines()
    
    if not machines_list:
        console.print("[red]No machines found[/red]")
        raise typer.Exit(1)
    
    # Filter by type if specified
    if worker:
        targets = filter_machines(machines_list, "worker")
    elif web:
        targets = filter_machines(machines_list, "web")
    else:
        targets = machines_list
    
    if not targets:
        console.print("[yellow]No matching machines found[/yellow]")
        raise typer.Exit(1)
    
    # Select machine
    machine_id = select_machine_interactive(targets)
    if not machine_id:
        raise typer.Exit(1)
    
    console.print(f"[bold blue]🔐 Connecting to machine {machine_id[:12]}...[/bold blue]")
    run_fly_command(["ssh", "console", "-s", machine_id])


@app.command()
def db():
    """Connect to Postgres database"""
    console.print("[bold blue]🗄️  Connecting to database...[/bold blue]")
    run_fly_command(["postgres", "connect", "-a", "lynch-postgres"])


@app.command()
def secrets():
    """Manage secrets (use subcommands: list, set)"""
    # This is just a parent command - users will use `secrets list` or `secrets set`
    console.print("[yellow]Use 'bag prod secrets list' or 'bag prod secrets set'[/yellow]")


# Secrets subcommands
secrets_app = typer.Typer(help="Manage Fly.io secrets")
app.add_typer(secrets_app, name="secrets")


@secrets_app.command("list")
def secrets_list():
    """List all secrets"""
    run_fly_command(["secrets", "list"])


@secrets_app.command("set")
def secrets_set(
    key: str = typer.Argument(..., help="Secret key"),
    value: str = typer.Argument(..., help="Secret value"),
):
    """Set a secret value"""
    console.print(f"[bold blue]Setting secret {key}...[/bold blue]")
    run_fly_command(["secrets", "set", f"{key}={value}"])
    console.print("[bold green]✓ Secret set![/bold green]")
