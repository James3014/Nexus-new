#!/usr/bin/env python3
import requests
import json
import sys
import os
import time
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.text import Text

# [SOTA 10/10] Nexus Singularity CLI Command Center v30.3
# Direct Neural Interface to the Nexus OS Kernel.

console = Console()
API_BASE = os.getenv("NEXUS_HUB_URL", "http://127.0.0.1:5001")
TENANT_ID = "Tenant_Friend"

def print_header():
    console.clear()
    header_text = Text("NEXUS SINGULARITY OS [v30.3]", style="bold cyan")
    header_text.append(" | ", style="white")
    header_text.append("SOTA 85.5%", style="bold green")
    header_text.append(" | ", style="white")
    header_text.append("ACTIVE HUB MODE", style="bold magenta")
    
    console.print(Panel(header_text, border_style="blue", expand=False))
    console.print("[dim]Type your question directly, or use /commands for governance.[/dim]\n")

def get_ps():
    try:
        res = requests.get(f"{API_BASE}/os/ps")
        procs = res.json()
        table = Table(title="Nexus Active Governance Processes", border_style="dim")
        table.add_column("PID", style="cyan")
        table.add_column("Tenant", style="green")
        table.add_column("Action", style="magenta")
        table.add_column("Status", style="yellow")
        
        for p in procs:
            table.add_row(str(p['pid']), p['tenant'], str(p['action']), "RUNNING")
        
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error fetching process list: {e}[/red]")

def nexus_consult(question):
    try:
        with console.status("[bold blue]Nexus is reasoning...", spinner="dots"):
            res = requests.post(
                f"{API_BASE}/consult",
                headers={"X-Tenant-ID": TENANT_ID},
                json={"question": question}
            )
            res.encoding = 'utf-8' # Force UTF-8 decoding
            data = res.json()
        
        console.print(Panel(Markdown(data['answer']), title="[bold magenta]Nexus Consultant[/bold magenta]", border_style="magenta"))
    except Exception as e:
        console.print(f"[red]Consultation failed: {e}[/red]")

def nexus_govern(repo_url):
    try:
        res = requests.post(
            f"{API_BASE}/govern",
            headers={"X-Tenant-ID": TENANT_ID},
            json={"repo": repo_url}
        )
        data = res.json()
        console.print(f"[bold green]Governance Task Deployed![/bold green] TID: {data['task_id']}")
    except Exception as e:
        console.print(f"[red]Governance deployment failed: {e}[/red]")

def nexus_query(pattern):
    try:
        res = requests.post(
            f"{API_BASE}/query",
            headers={"X-Tenant-ID": TENANT_ID},
            json={"pattern": pattern}
        )
        data = res.json()
        console.print(f"[bold cyan]Query Dispatched to Reflex Core.[/bold cyan] PID: {data['task_id']}")
    except Exception as e:
        console.print(f"[red]Query failed: {e}[/red]")

def main_loop():
    print_header()
    
    while True:
        try:
            cmd = Prompt.ask("[bold cyan]Nexus[/bold cyan]")
            
            if not cmd:
                continue
                
            if cmd.lower() in ["/exit", "/quit", "exit", "quit"]:
                console.print("[bold yellow]Singularity Session Terminated. Nexus Standing By.[/bold yellow]")
                break
            elif cmd == "/ps":
                get_ps()
            elif cmd == "/clear":
                print_header()
            elif cmd.startswith("/govern"):
                parts = cmd.split(maxsplit=1)
                if len(parts) > 1:
                    nexus_govern(parts[1])
                else:
                    console.print("[red]Usage: /govern <repo_url>[/red]")
            elif cmd.startswith("/query"):
                parts = cmd.split(maxsplit=1)
                if len(parts) > 1:
                    nexus_query(parts[1])
                else:
                    console.print("[red]Usage: /query <pattern>[/red]")
            elif cmd == "/help":
                console.print("[bold white]Available Commands:[/bold white]")
                console.print("  /ps             Show active governance processes")
                console.print("  /govern <url>   Deploy governance to a repo")
                console.print("  /query <pat>    Search code symbols using Rust Reflex")
                console.print("  /clear          Clear screen")
                console.print("  /exit           Terminate session")
                console.print("  <any text>      Consult the AI Advisor")
            else:
                nexus_consult(cmd)
                
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Nexus Hibernating...[/bold yellow]")
            break
        except Exception as e:
            console.print(f"[red]Loop Error: {e}[/red]")

if __name__ == "__main__":
    # [SOTA 30.7] Robust UTF-8 Hardening for Stdin/Stdout
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        
    main_loop()
