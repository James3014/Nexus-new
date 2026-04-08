import click
import json
from nexus.cli.utils import _get_service, REPO_ROOT

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
