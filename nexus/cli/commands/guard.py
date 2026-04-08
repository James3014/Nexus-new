import click
import json
from nexus.cli.utils import _get_service, REPO_ROOT

@click.group(name="guard")
def guard_group():
    """🛡️ 抗幻覺門禁與多代理共識 (v23)"""
    pass

@guard_group.command(name="validate")
@click.option("--task-id", default="manual-audit")
@click.option("--file", "target_file")
@click.option("--symbol", "target_symbol")
@click.option("--risk", "risk_prior", default=0.4, type=float)
def guard_validate_cmd(task_id, target_file, target_symbol, risk_prior):
    """執行多代理共識校驗 (Consensus Guard)"""
    from nexus_swarm.guard.consensus_guard import ConsensusGuard
    guard = ConsensusGuard()
    mock_res = {"target_file": target_file, "target_symbol": target_symbol}
    res = guard.validate_scenario(task_id, mock_res, risk_score_prior=risk_prior)
    click.echo(json.dumps(res, indent=2))
