#!/usr/bin/env python3
"""
manage.py — CLI management tool for the clinic microservices stack.

Usage (after activating the venv):
    python manage.py up          # Build and start all services
    python manage.py down        # Stop and remove containers
    python manage.py restart     # Restart all services
    python manage.py build       # Rebuild images without starting
    python manage.py status      # Show running containers
    python manage.py logs [svc]  # Tail logs (optionally for one service)
    python manage.py health      # Check health of all services via admin API
    python manage.py summary     # Print clinic dashboard summary
"""

import argparse
import subprocess
import sys
import os
import json
from pathlib import Path

try:
    import httpx
    from rich.console import Console
    from rich.table import Table
    from rich import print as rprint
    from dotenv import load_dotenv
except ImportError:
    print("Dependencies missing. Run: pip install -r requirements-manage.txt")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
ENV_FILE   = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

ADMIN_URL  = os.getenv("ADMIN_SERVICE_URL", "http://localhost:9000")
COMPOSE    = ["docker", "compose"]

console = Console()

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command with live output."""
    console.print(f"[bold cyan]$ {' '.join(cmd)}[/bold cyan]")
    return subprocess.run(cmd, cwd=BASE_DIR, check=check)

def get(path: str) -> dict:
    try:
        r = httpx.get(f"{ADMIN_URL}{path}", timeout=8)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        console.print(f"[red]Cannot reach admin service at {ADMIN_URL}. Is the stack running?[/red]")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP {e.response.status_code}: {e.response.text}[/red]")
        sys.exit(1)

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_up(args):
    """Build images and start all services in detached mode."""
    run(COMPOSE + ["up", "--build", "-d"])
    console.print("\n[bold green]✔  Stack is up.[/bold green]")
    console.print("  Eureka:      http://localhost:8761")
    console.print("  Admin API:   http://localhost:9000/docs")
    console.print("  Grafana:     http://localhost:3000")
    console.print("  Prometheus:  http://localhost:9090")


def cmd_down(args):
    """Stop and remove containers (keeps volumes)."""
    run(COMPOSE + ["down"])
    console.print("[bold yellow]Stack stopped.[/bold yellow]")


def cmd_restart(args):
    """Restart all containers."""
    run(COMPOSE + ["restart"])
    console.print("[bold green]Stack restarted.[/bold green]")


def cmd_build(args):
    """Rebuild all Docker images without starting."""
    run(COMPOSE + ["build"])
    console.print("[bold green]Images rebuilt.[/bold green]")


def cmd_status(args):
    """Show running containers in a formatted table."""
    result = subprocess.run(
        COMPOSE + ["ps", "--format", "json"],
        cwd=BASE_DIR, capture_output=True, text=True
    )
    lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
    if not lines:
        console.print("[yellow]No containers running.[/yellow]")
        return

    table = Table(title="Docker Compose Services", show_lines=True)
    table.add_column("Service",  style="cyan",  no_wrap=True)
    table.add_column("Status",   style="green")
    table.add_column("Ports",    style="yellow")
    table.add_column("Image",    style="dim")

    for line in lines:
        try:
            c = json.loads(line)
            status_color = "green" if "healthy" in c.get("Health","").lower() or "running" in c.get("State","").lower() else "red"
            table.add_row(
                c.get("Service", c.get("Name", "-")),
                f"[{status_color}]{c.get('State','?')} ({c.get('Health','–')})[/{status_color}]",
                c.get("Publishers", c.get("Ports", "-")) if isinstance(c.get("Publishers", c.get("Ports", "-")), str) else str(c.get("Publishers","-")),
                c.get("Image", "-"),
            )
        except (json.JSONDecodeError, KeyError):
            pass

    console.print(table)


def cmd_logs(args):
    """Tail logs for all services or a specific one."""
    target = [args.service] if args.service else []
    run(COMPOSE + ["logs", "-f", "--tail=50"] + target, check=False)


def cmd_health(args):
    """Call /health/services on the admin API and display results."""
    data = get("/health/services")

    table = Table(title="Services Health", show_lines=True)
    table.add_column("Service", style="cyan")
    table.add_column("Status",  style="bold")
    table.add_column("Detail")

    for svc, info in data.items():
        status_str = info.get("status", "?")
        color = "green" if status_str == "UP" else "red"
        detail = json.dumps({k: v for k, v in info.items() if k != "status"}) if len(info) > 1 else ""
        table.add_row(svc, f"[{color}]{status_str}[/{color}]", detail)

    console.print(table)


def cmd_summary(args):
    """Fetch clinic stats from the admin API dashboard summary."""
    data = get("/admin/summary")

    table = Table(title="Clinic Dashboard Summary", show_lines=True)
    table.add_column("Metric",  style="cyan")
    table.add_column("Count",   style="bold green", justify="right")

    table.add_row("Patients",   str(data.get("total_patients",   "-")))
    table.add_row("Médecins",   str(data.get("total_medecins",   "-")))
    table.add_row("Rendez-vous", str(data.get("total_rendezvous", "-")))

    console.print(table)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="manage.py",
        description="CLI manager for the clinic microservices stack.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("up",       help="Build and start all services")
    sub.add_parser("down",     help="Stop and remove containers")
    sub.add_parser("restart",  help="Restart all services")
    sub.add_parser("build",    help="Rebuild images without starting")
    sub.add_parser("status",   help="Show running containers")

    logs_p = sub.add_parser("logs", help="Tail logs")
    logs_p.add_argument("service", nargs="?", help="Service name (optional)")

    sub.add_parser("health",   help="Check health of all services")
    sub.add_parser("summary",  help="Print clinic dashboard summary")

    args = parser.parse_args()

    dispatch = {
        "up":      cmd_up,
        "down":    cmd_down,
        "restart": cmd_restart,
        "build":   cmd_build,
        "status":  cmd_status,
        "logs":    cmd_logs,
        "health":  cmd_health,
        "summary": cmd_summary,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
