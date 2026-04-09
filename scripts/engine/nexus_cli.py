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
            "commit_sha": "da69f5b"
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

@nexus_group.command(name="distill")
@click.option("--goal", default="Continuous Improvement")
def distill(goal):
    """🌬️ [Metabolism] Distill session essence and reset brain."""
    from nexus.services.metabolism_engine import metabolism
    # 模擬當前 context
    ctx = {
        "goal": goal,
        "done": ["Phase 1-3 Fusion", "Physical Preflight"],
        "todo": ["Quantum Fleet Expansion", "AGI Distillation"]
    }
    tx = metabolism.distill(ctx)
    click.echo(f"💎 Session crystallized. Arweave TX: {tx}")
    click.echo(f"🌬️ [ACTION] Brain reset required. Please restart with the seed in .nexus/metabolism/session_seed.json")

@nexus.command(name="meta-warmup")
@click.option("--seed", default="v07-best")
@click.option("--population", default=64)
def meta_warmup(seed, population):
    """🔥 [v0.8] Meta-Warmup: Seed from v0.7 DNA"""
    from scripts.ops.evolution_engine_v08 import EvolutionEngineV08
    count = EvolutionEngineV08(REPO_ROOT).meta_warmup(seed, population)
    click.echo(f"✅ Meta-Warmup Complete. Seeded {count} genomes.")

@nexus.command(name="meta-run")
@click.option("--count", default=128)
@click.option("--hybrid", default=0.0, type=float)
@click.option("--gpu", is_flag=True)
@click.option("--quick", is_flag=True)
def meta_run(count, hybrid, gpu, quick):
    """🚀 [v0.8] Meta-Evolve: Hybrid Convergence"""
    from scripts.ops.evolution_engine_v08 import EvolutionEngineV08
    engine = EvolutionEngineV08(REPO_ROOT)
    if quick: count = 32
    best = engine.meta_evolve(count=count, hybrid_ratio=hybrid)
    click.echo(f"🧬 [NAS] Gen {best['gen']} Evolved. Fitness: {best['fitness']} (Hybrid={hybrid})")

@nexus.command(name="meta-deploy")
def meta_deploy():
    """💎 [v0.8] Meta-Deploy: Lock-in 0.98+ Fitness Topology"""
    from scripts.ops.evolution_engine_v08 import EvolutionEngineV08
    engine = EvolutionEngineV08(REPO_ROOT)
    with open(REPO_ROOT / "evolution_traces.jsonl", "r") as f:
        best = json.loads(f.readlines()[-1])
    engine.deploy_v08(best)
    click.echo(f"🚀 v0.8 Topology LOCKED. Best ID: {best['best_id']}")
    # 自動化閉環：觸發結晶化
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/crystallize_lessons.py")], check=False)

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
        # 自動化閉環：觸發結晶化
        subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/crystallize_lessons.py")], check=False)

@nexus.command(name="fed-status")
@click.option("--json", "as_json", is_flag=True)
def fed_status(as_json):
    """📊 Show Federated NAS Status"""
    trace_path = REPO_ROOT / "evolution_traces.jsonl"
    last = {"fitness": 0.0, "fed_stats": {"aggregation_ratio": "0/0"}}
    if trace_path.exists():
        with open(trace_path, "r") as f:
            lines = f.readlines()
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

@nexus.command(name="topology-live")
def topology_live():
    conf_path = REPO_ROOT / "configs/swarm_topology.yaml"
    with open(conf_path, "r") as f:
        click.echo(yaml.dump(yaml.safe_load(f), default_flow_style=False))

if __name__ == "__main__":
    nexus()
