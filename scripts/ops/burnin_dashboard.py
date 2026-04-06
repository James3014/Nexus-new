#!/usr/bin/env python3
# 🛡️ Nexus v23 Burn-in Real-time HUD (Premium Edition)
# [ARCH-EVO: v23 WISDOM DASHBOARD]

import os
import json
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from datetime import datetime

console = Console()
METRICS_DIR = Path(".nexus/metrics")
FEEDBACK_FILE = METRICS_DIR / "feedback_events.jsonl"
STATS_FILE = Path("nexus_swarm/wisdom/learner_stats.json")

def load_metrics():
    events = []
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r") as f:
            for line in f:
                try: events.append(json.loads(line))
                except: pass
    
    stats = {}
    if STATS_FILE.exists():
        with open(STATS_FILE, "r") as f:
            try: stats = json.load(f)
            except: pass
    return events, stats

def make_layout() -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3)
    )
    layout["body"].split_row(
        Layout(name="stats", ratio=1),
        Layout(name="events", ratio=1)
    )
    return layout

def generate_dashboard():
    events, stats = load_metrics()
    
    # 1. Progress Bar
    event_count = len(events)
    target = 100
    progress = Progress(
        TextColumn("[bold cyan]Burn-in Progress[/]"),
        BarColumn(bar_width=40),
        TextColumn("[bold white]{task.completed}/{task.total}[/]"),
        TextColumn("[bold yellow]({task.percentage:>3.0f}%)[/]")
    )
    progress.add_task("Events", total=target, completed=min(event_count, target))
    
    # 2. Pattern Stats Table
    table = Table(title="🧠 Neural Wisdom Distribution", expand=True)
    table.add_column("Pattern ID", style="cyan")
    table.add_column("Score (Bypass)", justify="right", style="green")
    table.add_column("Confidence", justify="right", style="magenta")
    table.add_column("Feedback (C/FP/M)", justify="right")

    for pid, s in stats.items():
        table.add_row(
            pid,
            f"{s.get('bypass_score', 0):.2f}",
            f"{s.get('confidence', 0):.2f}",
            f"{s.get('correct_count', 0)}/{s.get('fp_count', 0)}/{s.get('missed_count', 0)}"
        )

    # 3. Recent Events
    event_table = Table(title="⚡ Latest Feedback Events", expand=True)
    event_table.add_column("Timestamp", style="dim")
    event_table.add_column("Task ID")
    event_table.add_column("Type", style="bold")
    
    for e in events[-8:][::-1]:
        ts = datetime.fromtimestamp(e.get('timestamp', 0)).strftime("%H:%M:%S")
        event_table.add_row(ts, e.get('task_id', 'N/A')[:15], e.get('feedback_type', 'N/A'))

    return Panel(progress, title="🚀 v23 Burn-in Accelerator Status"), table, event_table

if __name__ == "__main__":
    layout = make_layout()
    try:
        with Live(layout, refresh_per_second=1, screen=True):
            while True:
                header, stats_table, event_table = generate_dashboard()
                layout["header"].update(header)
                layout["stats"].update(Panel(stats_table, title="Knowledge Stats"))
                layout["events"].update(Panel(event_table, title="Live Events Stream"))
                layout["footer"].update(Panel(f"[dim]CWD: {os.getcwd()} | ID: Nexus v23-BurnIn[/]", border_style="dim"))
                time.sleep(2)
    except KeyboardInterrupt:
        pass
