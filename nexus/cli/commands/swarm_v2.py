import click
import json
import requests
from nexus.cli.utils import _get_service, REPO_ROOT

@click.group(name="swarm_v2")
def swarm_v2_group():
    """🛡️ 分佈式蜂群治理 (NSP v0.1 Distributed Cluster)"""
    pass

@swarm_v2_group.command("status")
def swarm_v2_status():
    """查看分佈式叢集狀態"""
    try:
        resp = requests.get("http://localhost:9100/cluster/status", timeout=2)
        click.echo(json.dumps(resp.json(), indent=2))
    except Exception as e:
        click.echo(f"❌ Swarm Manager not reachable: {e}")

@click.group(name="eternal")
def eternal_group():
    """🛡️ Arweave 永恆記憶管理 (v23 Eternal Neural Swarm)"""
    pass

@eternal_group.command("sync")
def eternal_sync():
    """同步教訓到 Arweave"""
    _get_service().swarm_wave1()
    click.echo("✅ [Eternal] Sync initiated.")
