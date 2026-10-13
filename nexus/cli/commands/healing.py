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
def healing_group():
    """🚑 預測性自癒與系統壓力預報 (v23)"""
    pass

@healing_group.command(name="forecast")
def healing_forecast_cmd():
    """執行全球風險預測掃描 (Predictive Heal)"""
    from nexus_swarm.healing.predictive_healer import PredictiveHealer
    healer = PredictiveHealer()
    res = healer.forecast_risk()
    click.echo(json.dumps(res, indent=2))
