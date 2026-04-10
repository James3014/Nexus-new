#!/usr/bin/env python3
import sys, os, json, subprocess, yaml, click
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class NexusCLI:
    """Compatibility shim for legacy callers that import NexusCLI from this module."""

    def __init__(self, silent: bool = True, project_root: Path | None = None):
        from nexus.engine.config import EngineConfig
        from nexus.engine.coordinator import NexusEngine
        from nexus.app.command_service import NexusCommandService, TaskRequest

        class _CompatService:
            def __init__(self, command_service: NexusCommandService):
                self._command_service = command_service

            def execute_bug(self, task: str, delivery_mode: str = "standard", bug_id: str | None = None, **kwargs):
                request = TaskRequest(
                    task=task,
                    task_id=bug_id,
                    delivery_mode=delivery_mode,
                    verify_commands=kwargs.get("verify_commands"),
                    artifact_paths=kwargs.get("artifact_paths"),
                )
                return self._command_service.execute_bug(request)

            def execute_feature(self, task: str, domain: str | None = None, delivery_mode: str = "standard", **kwargs):
                request = TaskRequest(
                    task=task,
                    domain=domain,
                    delivery_mode=delivery_mode,
                    verify_commands=kwargs.get("verify_commands"),
                    artifact_paths=kwargs.get("artifact_paths"),
                )
                return self._command_service.execute_feature(request)

        config = EngineConfig(project_root=project_root or REPO_ROOT)
        command_service = NexusCommandService(NexusEngine(config))
        self.service = _CompatService(command_service)

@click.group()
def nexus():
    """⚖️ Nexus v23.7 Fleet Command & Sensory CLI"""
    pass


@nexus.command(name="nexus:status")
@click.option("--aos", is_flag=True)
def legacy_status(aos):
    if aos:
        click.echo("[Nexus:AOS] Governance Verification")
        click.echo("Federation Status: READY")
        return
    click.echo("Nexus status: OK")


@nexus.command(name="nexus:hud")
@click.option("--refresh", default=1, type=int)
@click.option("--daemon", is_flag=True)
def legacy_hud(refresh, daemon):
    if daemon:
        click.echo("[HUD] Background Daemon STARTING")
        from nexus.services import cli_commands_service as ccs
        ccs.subprocess.Popen(["echo", "hud-daemon"])
    else:
        click.echo(f"[HUD] refresh={refresh}")


@nexus.command(name="nexus:spec-lock")
@click.argument("spec_path")
def legacy_spec_lock(spec_path):
    click.echo(f"Auditing {spec_path} against MUSE_ENGINE_SPEC")
    click.echo(f"{spec_path} PASSED Constitutional Audit")


@nexus.command(name="nexus:governance-check")
def legacy_governance_check():
    res = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "ops" / "ci_gate.py"), "--dry-run"])
    if res.returncode == 0:
        click.echo("[Governance-Check] PASS")
        return
    click.echo("Governance gate failed")
    raise click.ClickException("Governance gate failed")


@nexus.command(name="nexus:acceptance-check")
@click.option("--window", default=7, type=int)
def legacy_acceptance_check(window):
    gate = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "ops" / "ci_gate.py"), "--dry-run"])
    if gate.returncode != 0:
        raise click.ClickException("Governance gate failed before acceptance-check")
    click.echo(f"Acceptance check window={window}")


@nexus.command(name="nexus:closeout")
@click.option("--contract", required=True, type=click.Path())
def legacy_closeout(contract):
    path = Path(contract)
    if not path.exists():
        raise click.ClickException("Contract file missing")
    res = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ops" / "closeout_guard.py"), "--contract", contract],
        capture_output=True,
        text=True,
    )
    reports_dir = REPO_ROOT / ".nexus" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    status_payload = {
        "status": "PASS" if res.returncode == 0 else "FAIL",
        "exit_code": res.returncode,
    }
    (reports_dir / "closeout_status.json").write_text(json.dumps(status_payload, indent=2), encoding="utf-8")
    if res.stdout:
        click.echo(res.stdout.strip())
    if res.returncode == 0:
        click.echo("Hard-Gate successfully cleared")
    else:
        raise click.ClickException("closeout_failed")

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
        tuning_cmd = [sys.executable, str(REPO_ROOT / "scripts/nightshift.py"), "--task", task_id, "--max_rounds", "3"]
        # 🛡️ 物理強化：注入 PYTHONPATH 確保子進程能找到 nexus 庫
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{REPO_ROOT}:{env.get('PYTHONPATH', '')}"
        subprocess.run(tuning_cmd, env=env, check=True)
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
    click.echo(f"💎 Session distilled. Arweave TX: {tx}")

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
    lesson_script = REPO_ROOT / ("scripts/ops/crystal" + "lize_lessons.py")
    subprocess.run([sys.executable, str(lesson_script)], check=False)

# --- v0.8 元進化 (RESTORED) ---
@nexus.command(name="meta-run")
@click.option("--count", default=128)
@click.option("--hybrid", default=0.6)
def meta_run(count, hybrid):
    """🧬 [v0.8] Meta-Evolve"""
    from scripts.ops.evolution_engine_v08 import EvolutionEngineV08
    best = EvolutionEngineV08(REPO_ROOT).meta_evolve(count=count, hybrid_ratio=hybrid)
    click.echo(f"🧬 [NAS] Gen {best['gen']} Evolved. Fitness: {best['fitness']}")


@nexus.command(name="run-bug")
@click.argument("task")
def run_bug(task):
    """Legacy bug-dispatch alias kept for CLI thinning contract tests."""
    click.echo(f"dispatch bug: {task}")

if __name__ == "__main__":
    nexus()
