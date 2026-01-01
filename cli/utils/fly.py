"""
Fly.io utility functions for bag CLI
"""
import json
import subprocess
import typer
from typing import List, Dict, Optional, Any
from rich.console import Console
from rich.prompt import Prompt

console = Console()


def run_fly_command(args: List[str], capture_output: bool = False) -> Optional[str]:
    """Run a fly command with the given arguments."""
    cmd = ["fly"] + args
    
    if capture_output:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Error running fly command:[/red] {result.stderr}")
            raise typer.Exit(1)
        return result.stdout
    else:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise typer.Exit(1)
        return None


def get_machines() -> List[Dict]:
    """Get list of machines from fly machines list -j"""
    try:
        output = run_fly_command(["machines", "list", "-j"], capture_output=True)
        machines = json.loads(output)
        return machines
    except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
        console.print(f"[red]Failed to get machines:[/red] {e}")
        return []


def filter_machines(machines: List[Dict], machine_type: str) -> List[Dict]:
    """Filter machines by type (web/worker).
    
    Workers are identified by metadata.role = "worker".
    Web/app machines are identified by metadata.fly_process_group = "app" or lack of worker role.
    """
    if machine_type == "worker":
        return [m for m in machines if m.get("config", {}).get("metadata", {}).get("role") == "worker"]
    elif machine_type == "web":
        # Web machines have fly_process_group="app" and no worker role
        return [m for m in machines 
                if m.get("config", {}).get("metadata", {}).get("fly_process_group") == "app"
                or (m.get("config", {}).get("metadata", {}).get("role") != "worker" 
                    and "worker" not in m.get("name", "").lower())]
    return machines


def get_running_jobs_from_prod_db() -> Dict[str, Dict[str, Any]]:
    """
    Query prod DB for running jobs via fly ssh.
    Returns dict keyed by machine ID -> job info.
    """
    from rich.status import Status
    import base64
    
    # Python script to query the DB and output JSON (uses psycopg v3)
    query_script = '''
import json, os, psycopg
try:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT claimed_by, job_type, progress_pct FROM background_jobs WHERE status = 'running' AND claimed_by IS NOT NULL")
    rows = cur.fetchall()
    print(json.dumps([{"c": r[0], "t": r[1], "p": r[2]} for r in rows]))
except:
    print("[]")
'''
    # Base64 encode to avoid shell quoting issues
    script_b64 = base64.b64encode(query_script.encode()).decode()
    
    try:
        with Status("[dim]Fetching job status...[/dim]", console=console):
            result = subprocess.run(
                ["fly", "ssh", "console", "-a", "lynch-stock-screener", "-g", "app", "-C", 
                 f"python3 -c 'import base64; exec(base64.b64decode(\"{script_b64}\").decode())'"],
                capture_output=True,
                text=True,
                timeout=15
            )
        
        if result.returncode != 0:
            print(f"DEBUG: SSH failed with code {result.returncode}")
            print(f"DEBUG: stderr={result.stderr}")
            return {}
        
        # Parse JSON output - look for the JSON array line
        import json as json_mod
        jobs = {}
        print(f"DEBUG: stdout lines={result.stdout.strip().split(chr(10))}")
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.startswith('['):
                try:
                    rows = json_mod.loads(line)
                    print(f"DEBUG: parsed rows={rows}")
                    for row in rows:
                        claimed_by = row.get('c', '')
                        if claimed_by:
                            # Extract machine ID from "{machine_id}-{pid}"
                            machine_id = claimed_by.rsplit('-', 1)[0] if '-' in claimed_by else claimed_by
                            jobs[machine_id] = {
                                'job_type': row.get('t', '?'),
                                'progress_pct': row.get('p'),
                            }
                            print(f"DEBUG: added job {machine_id} -> {jobs[machine_id]}")
                except json_mod.JSONDecodeError as e:
                    print(f"DEBUG: JSON decode error: {e}")
                    pass
        
        print(f"DEBUG: final jobs={jobs}")
        return jobs
        
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"DEBUG: Exception: {e}")
        return {}


def select_machine_interactive(machines: List[Dict], job_info: Dict[str, Dict] = None) -> Optional[str]:
    """Interactive machine selection with optional job info display."""
    if not machines:
        console.print("[yellow]No machines found[/yellow]")
        return None
    
    if len(machines) == 1:
        return machines[0]["id"]
    
    print("\nWorkers:")
    for idx, machine in enumerate(machines, 1):
        name = machine.get("name", "unknown")
        machine_id = machine["id"]
        
        # Check for job info
        job_str = ""
        if job_info and machine_id in job_info:
            job = job_info[machine_id]
            job_type = job.get('job_type', '?')
            progress = job.get('progress_pct')
            if progress:
                job_str = f" -> {job_type} ({progress}%)"
            else:
                job_str = f" -> {job_type}"
        elif job_info is not None:
            job_str = " (idle)"
        
        print(f"  {idx}. {name}{job_str}")
    
    # Use simple input
    print()
    try:
        choice = input(f"Select [1-{len(machines)}] (1): ").strip() or "1"
        if choice.isdigit() and 1 <= int(choice) <= len(machines):
            return machines[int(choice) - 1]["id"]
        else:
            print("Invalid choice, using 1")
            return machines[0]["id"]
    except (KeyboardInterrupt, EOFError):
        return None

