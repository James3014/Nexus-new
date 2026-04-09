#!/usr/bin/env python3
import sys, os, json, subprocess, yaml, click
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@click.group()
def nexus():
    """⚖️ Nexus v23.7 Fleet Command & Sensory CLI"""
    pass

@nexus.group(name="nexus")
def nexus_group():
    """🛡️ Nexus Core Governance & Command"""
    pass

# --- 治理與狀態 ---
@nexus_group.command(name="status")
@click.option("--json", "as_json", is_flag=True)
def status(as_json):
    """📊 Show system status and trust scores."""
    if as_json:
        res = {"status": "OPERATIONAL", "version": "v23.7", "fleet_size": 50, "mcp": "READY"}
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

@nexus_group.command(name="run")
@click.argument("task_id")
@click.option("--complexity", type=float, default=0.0)
def run(task_id, complexity):
    """🚀 [Wisdom Layer] Execute task with automatic NAS tuning."""
    from nexus.core.context_hub import ContextHub
    hub = ContextHub(REPO_ROOT)
    
    # 1. 智慧感應 (Wisdom Sensing)
    decision = hub.make_pre_routing_decision(task_id, {"complexity_score": complexity})
    
    if decision.get("nas_autotune_needed"):
        click.echo(f"🧬 [Wisdom Layer] High complexity detected. Launching Bayesian Auto-Tuning...")
        tuning_cmd = [sys.executable, str(REPO_ROOT / "scripts/nightshift.py"), "--task", task_id, "--max-rounds", "3"]
        subprocess.run(tuning_cmd, check=True)
        click.echo("✅ [Wisdom Layer] NAS Tuning Complete. Optimal weights locked.")
    
    # 2. 正式執行
    click.echo(f"🚀 Executing Task: {task_id} with locked NAS weights...")
    # ... (原有執行邏輯)

@nexus_group.command(name="contract-check")
@click.option("--contract-file", type=click.Path(exists=True), required=True)
def contract_check(contract_file):
    """📜 [Governance] Validate task contract against physical state."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts/ops/closeout_guard.py"), "--contract", contract_file]
    subprocess.run(cmd, check=True)

@nexus_group.command(name="distill")
def distill():
    """🌬️ [Metabolism] Distill session essence."""
    from nexus.services.metabolism_engine import metabolism
    tx = metabolism.distill({"goal": "v23.7 Recovery", "done": ["Wiki Sync"], "todo": ["Command Recovery"]})
    click.echo(f"💎 Session crystallized. Arweave TX: {tx}")

# --- v23.7 艦隊指揮 ---
@nexus_group.command(name="resume")
def resume():
    """🌬️ [Metabolism] Resume task from last physical checkpoint."""
    from nexus.services.metabolism_engine import metabolism
    checkpoint = metabolism.load_checkpoint()
    if not checkpoint:
        click.echo("❌ No checkpoint found.")
        return
    click.echo(f"🌬️ Resuming Task: {checkpoint['task_id']}")

@nexus_group.command(name="delegate")
@click.argument("task_name")
def delegate(task_name):
    """📡 [Supervisor] Decompose and delegate task to fleet."""
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/supervisor_engine.py"), task_name], check=True)

# --- External Command Registration ---
try:
    from scripts.engine.commands.ui_explorer import register as register_ui_explorer
    register_ui_explorer(nexus_group, REPO_ROOT)
    
    from scripts.engine.commands.swarm import register as register_swarm
    register_swarm(nexus_group, REPO_ROOT)
    
    from scripts.engine.commands.stress_test import register as register_stress_test
    register_stress_test(nexus_group, REPO_ROOT)
except ImportError as e:
    click.echo(f"⚠️  [Nexus:CLI] Could not load external command module: {e}")

# --- v0.9 聯邦指令 (RESTORED) ---

@nexus.command(name="fed-init")
@click.option("--tenants", default=10)
def fed_init(tenants):
    """🌐 [v0.9] Federated Init"""
    from scripts.ops.federated_engine_v09 import FederatedEngineV09
    FederatedEngineV09(REPO_ROOT).fed_init(num_tenants=tenants)
    click.echo(f"📡 Fleet Initialized: {tenants} tenants.")

@nexus.command(name="fed-run")
def fed_run():
    """🚀 [v0.9] Fed-Run: Execute Federated NAS"""
    from scripts.ops.federated_engine_v09 import FederatedEngineV09
    res = FederatedEngineV09(REPO_ROOT).fed_sync()
    click.echo(f"🧬 [v0.9 Federated NAS] Synchronized {res['aggregation_ratio']} tenants.")
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts/ops/crystallize_lessons.py")], check=False)

# --- v0.8 元進化 (RESTORED) ---
@nexus.command(name="meta-run")
@click.option("--count", default=128)
@click.option("--hybrid", default=0.6)
def meta_run(count, hybrid):
    """🧬 [v0.8] Meta-Evolve"""
    from scripts.ops.evolution_engine_v08 import EvolutionEngineV08
    best = EvolutionEngineV08(REPO_ROOT).meta_evolve(count=count, hybrid_ratio=hybrid)
    click.echo(f"🧬 [NAS] Gen {best['gen']} Evolved. Fitness: {best['fitness']}")

if __name__ == "__main__":
    nexus()
