#!/usr/bin/env python3
import sys, os, json, subprocess, yaml, click
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@click.group()
def nexus():
    """⚖️ Nexus v23 NAS Hardened CLI"""
    pass

@nexus.group(name="nexus")
def nexus_group():
    """🛡️ Nexus Core Governance Commands"""
    pass

@nexus_group.command(name="status")
@click.option("--json", "as_json", is_flag=True)
def status(as_json):
    """📊 Show system status and trust scores."""
    if as_json:
        trace_path = REPO_ROOT / "evolution_traces.jsonl"
        last = {"fitness": 0.0, "meta_params": {"mutation_rate": 0.05}}
        if trace_path.exists():
            with open(trace_path, "r") as f:
                lines = f.readlines()
                if lines: last = json.loads(lines[-1])
        res = {
            "status": "OPERATIONAL",
            "nas_fitness": last.get("fitness", 0.0),
            "meta_mutation": last.get("meta_params", {}).get("mutation_rate", 0.05),
            "nexus_participation_ratio": 1.0,
            "commit_sha": "9ad067d"
        }
        click.echo(json.dumps(res, indent=2))
    else:
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/enterprise_audit_v22.py")], check=True)

@nexus_group.command(name="acceptance-check")
@click.option("--json", "as_json", is_flag=True)
def acceptance_check(as_json):
    """✅ Run full system acceptance check."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts/ops/nexus_acceptance_check.py")]
    if as_json: cmd.append("--json")
    subprocess.run(cmd, check=True)

@nexus.command(name="fed-init")
@click.option("--tenants", default=10)
@click.option("--dp-epsilon", default=1.0)
def fed_init(tenants, dp_epsilon):
    """🌐 [v0.9] Federated Init: Set up multi-tenant fleet"""
    from scripts.ops.federated_engine_v09 import FederatedEngineV09
    state = FederatedEngineV09(REPO_ROOT, epsilon=dp_epsilon).fed_init(num_tenants=tenants)
    click.echo(f"📡 [Federation] v0.9 Fleet Initialized: {tenants} tenants.")

@nexus.command(name="fed-run")
@click.option("--tenants", default=10)
@click.option("--dry-run", is_flag=True)
def fed_run(tenants, dry_run):
    """🚀 [v0.9] Fed-Run: Execute Federated NAS across fleets"""
    if dry_run:
        click.echo(f"🧪 [DRY-RUN] Simulating federation across {tenants} tenants...")
        click.echo(f"✅ Global DNA Delta computed (Simulated).")
    else:
        from scripts.ops.federated_engine_v09 import FederatedEngineV09
        res = FederatedEngineV09(REPO_ROOT).fed_sync()
        click.echo(f"🧬 [v0.9 Federated NAS] Synchronized {res['aggregation_ratio']} tenants.")

@nexus.command(name="fed-status")
@click.option("--json", "as_json", is_flag=True)
def fed_status(as_json):
    """📊 Show Federated NAS Status"""
    trace_path = REPO_ROOT / "evolution_traces.jsonl"
    last = {"fitness": 0.0, "fed_stats": {"aggregation_ratio": "0/0"}}
    if trace_path.exists():
        with open(trace_path, "r") as f:
            lines = f.readlines()
            # 尋找最新的 v0.9 紀錄
            for line in reversed(lines):
                data = json.loads(line)
                if data.get("version") == "v0.9":
                    last = data
                    break
    res = {
        "status": "OPERATIONAL",
        "nas_fitness": last.get("fitness", 0.0),
        "fed_aggregation": last.get("fed_stats", {}).get("aggregation_ratio", "0/0"),
        "version": "v0.9"
    }
    if as_json:
        click.echo(json.dumps(res, indent=2))
    else:
        click.echo(f"🌐 Federation Status: {res['status']}")
        click.echo(f"🏆 Best Fitness: {res['nas_fitness']}")

if __name__ == "__main__":
    nexus()
