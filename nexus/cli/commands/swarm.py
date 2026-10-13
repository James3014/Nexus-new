import click
import json
from nexus.cli.utils import _get_service, REPO_ROOT

import warnings as _archived_warnings

_archived_warnings.warn(
    "ARCHIVED 2026-10-13 (#1906): never-registered CLI module (nexus/cli/commands/*); live commands live in scripts/engine/commands; see ARCHIVED_2026-10-13.md. "
    "Scheduled for deletion; do not import.",
    DeprecationWarning,
    stacklevel=2,
)

@click.group(name="healing")
def swarm_group():
    """🚑 預測性自癒與系統壓力預報 (v23)"""
    pass

@swarm_group.command(name="forecast")
def healing_forecast_cmd():
    """執行全球風險預測掃描 (Predictive Heal)"""
    from nexus_swarm.healing.predictive_healer import PredictiveHealer
    healer = PredictiveHealer()
    res = healer.forecast_risk()
    click.echo(json.dumps(res, indent=2))

@click.group(name="swarm")
def swarm_group():
    """🛡️ Swarm Orchestration: 蜂群調度與路由管理"""
    pass

@swarm_group.command(name="dashboard")
@click.option("--workspace", default=".", help="工作區路徑")
def swarm_dashboard(workspace):
    """🚀 [Swarm:Cockpit] 啟動 nexus-desk 桌面監控中心"""
    import subprocess
    from pathlib import Path
    desk_dir = Path(workspace) / "nexus-desk"
    if not desk_dir.exists():
        click.echo(f"🛑 nexus-desk not found at {desk_dir}")
        return
    click.echo(f"🛡️ Launching Swarm Cockpit...")
    subprocess.run(["npm", "run", "tauri", "dev"], cwd=str(desk_dir))
