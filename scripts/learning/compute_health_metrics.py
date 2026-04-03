"""
🛡️ Nexus Health Metrics CLI: 計算各 Phase 健康指標 (P2-C)
"""

import click
import json
from pathlib import Path
from nexus.services.health_analyzer import compute_overall_health, compute_phase_health

@click.command()
@click.argument("workspace_root")
@click.option("--phase", default="all", help="Target phase (P/X/D/R/A/C) or 'all'")
@click.option("--days", default=90, help="Window days for metrics")
def main(workspace_root: str, phase: str, days: int):
    repo_root = Path(workspace_root)
    if not repo_root.exists():
        click.echo(json.dumps({"status": "error", "message": f"Path not found: {workspace_root}"}, indent=2))
        return

    if phase == "all":
        result = compute_overall_health(repo_root)
    else:
        result = compute_phase_health(repo_root, phase, days)
    
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
