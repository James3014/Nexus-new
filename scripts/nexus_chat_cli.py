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
    status_msg = "SOTA Stable"
    health = 100
    procs_count = 13
    
    try:
        res = requests.get(f"{API_BASE}/status", timeout=2)
        if res.status_code == 200:
            data = res.json()
            status_msg = data.get("status", status_msg)
            health = data.get("health", health)
            procs_count = data.get("processes", procs_count)
    except:
        pass # Fallback to defaults if proxy not yet fully available

    header_text = Text(f"NEXUS SINGULARITY OS [v31.3]", style="bold cyan")
    header_text.append("\n" + "━" * 40 + "\n", style="blue")
    header_text.append(f"STATUS: {status_msg} ", style="bold green")
    header_text.append(f"| HEALTH: {health}% ", style="bold yellow")
    header_text.append(f"| PROCESSES: {procs_count}\n", style="bold magenta")
    
    console.print(Panel(header_text, border_style="blue", expand=False, title="[bold white]Command Center[/bold white]"))
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
        
        # Handle both list and dict responses from proxy
        if isinstance(procs, dict):
            for pid, p in procs.items():
                table.add_row(str(pid), str(p.get('tenant', 'unknown')), str(p.get('action', 'bg')), "RUNNING")
        elif isinstance(procs, list):
            for p in procs:
                table.add_row(str(p.get('pid')), str(p.get('tenant', 'unknown')), str(p.get('action', 'bg')), "RUNNING")
        
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error fetching process list: {e}[/red]")

def nexus_consult(question):
    try:
        with console.status("[bold blue]Nexus is reasoning...", spinner="dots"):
            res = requests.post(
                f"{API_BASE}/consult",
                headers={"X-Tenant-ID": TENANT_ID},
                json={"question": question},
                timeout=30 # Prevent long hangs
            )
            res.encoding = 'utf-8'
            data = res.json()
        
        console.print(Panel(Markdown(data['answer']), title="[bold magenta]Nexus Consultant[/bold magenta]", border_style="magenta"))
    except requests.exceptions.ConnectionError:
        console.print(Panel("[bold red]ERROR[/bold red]: 無法連線至 Singularity Hub。\n[dim]請檢查 Host 端 (Sir) 是否已啟動 Proxy，或是環境變數 NEXUS_HUB_URL 是否正確。[/dim]", border_style="red", title="連線失敗"))
    except Exception as e:
        console.print(f"[bold red]Consultation failed:[/bold red] {str(e)}")

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
    
    # [SOTA 30.8] Standardize input for CJK resilience
    sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    
    while True:
        try:
            # Using rich's Prompt but with extra safety
            cmd = Prompt.ask("[bold cyan]Nexus[/bold cyan]").strip()
            
            if not cmd:
                continue
                
            if cmd.lower() in ["/exit", "/quit", "exit", "quit"]:
                console.print("[bold yellow]Singularity Session Terminated. Nexus Standing By.[/bold yellow]")
                break
            elif cmd == "/status":
                print_header()
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
                
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold yellow]Nexus Hibernating (User Exit)...[/bold yellow]")
            break
        except Exception as e:
            # [SOTA 30.8] No-Crash Policy: Display Panel instead of traceback
            console.print(Panel(f"[red]系統核心已攔截異常：[/red] {str(e)}\n[dim]Nexus 正在自我重啟輸入流...[/dim]", title="🛡️ 核心防護層", border_style="yellow"))
            time.sleep(0.5)

if __name__ == "__main__":
    # Ensure UTF8-Sentry
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
    main_loop()
