"""First-batch archive (2026-10-12, #1850): retired capabilities fail closed, visibly."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import get_executor
from nexus.services.capability_registry import (
    ARCHIVED_CAPABILITY_REASONS,
    SKIP_REASONS,
    build_default_mainchain_invokers,
)

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_REASONS = {
    "benchmark": "archived_fake_benchmark_2026-10-12",
    "stress_test": "archived_hollow_stress_test_2026-10-12",
    "ui_validator": "archived_ui_validator_2026-10-12",
    "learning_closure": "archived_hollow_learning_closure_2026-10-12",
    "federation": "archived_federation_2026-10-12",
    "oracle_shadow": "archived_oracle_shadow_2026-10-12",
}

# Planner nodes (learning_closure is executor-only, not a planner node).
PLANNER_NODES = ("benchmark", "stress_test", "ui_validator", "federation", "oracle_shadow")

ARCHIVED_MODULES = {
    "nexus.learning.federated_rag": "nexus/learning/federated_rag.py",
    "nexus.learning.lewm_predictor": "nexus/learning/lewm_predictor.py",
    "nexus.engine.federation": "nexus/engine/federation.py",
    "nexus.federation.fleet_manager": "nexus/federation/fleet_manager.py",
    "nexus.core.self_evolve_engine": "nexus/core/self_evolve_engine.py",
    "nexus.engine.red_team_audit": "nexus/engine/red_team_audit.py",
}

# Archived here first, then physically deleted 2026-10-17 (#2475, dead-code batch B4,
# ARCHIVED_2026-10-17_deadcode_b4.md): no longer importable at all.
DELETED_MODULES = {
    "nexus.services.aos_oracle": "nexus/services/aos_oracle.py",
}


def _plan(task_id: str = "arch-1") -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id=f"plan-{task_id}", task_id=task_id, constraints={})


def test_reason_table_matches_expected_and_whitelist():
    # The second batch (2026-10-13) extends the table; the first-batch rows are unchanged.
    assert EXPECTED_REASONS.items() <= ARCHIVED_CAPABILITY_REASONS.items()
    assert set(EXPECTED_REASONS.values()) <= SKIP_REASONS


@pytest.mark.parametrize("name", sorted(EXPECTED_REASONS))
def test_executor_emits_archived_reason(name):
    executor = get_executor(name)
    assert executor is not None, "archived capability must stay registered, not silently omitted"
    receipt = executor(_plan(), "any task")
    reason = EXPECTED_REASONS[name]
    assert receipt.capability_name == name
    assert receipt.selected is True
    assert receipt.invoked is False
    assert receipt.gate_passed is False
    assert receipt.outcome["skip_reason"] == reason
    assert receipt.outcome["error"] == reason
    assert receipt.outcome["semantic_status"] == "BLOCKED"
    assert receipt.outcome["archived"] is True
    assert receipt.outcome["evidence_refs"]


@pytest.mark.parametrize("name", PLANNER_NODES)
def test_planner_node_resolves_to_archived_skip(name):
    invokers = build_default_mainchain_invokers()
    assert name in invokers
    result = invokers[name]({"task_id": "arch-2", "escalate_triggered": True})
    assert result["skipped"] is True
    assert result["invoked"] is False
    assert result["skip_reason"] == EXPECTED_REASONS[name]
    assert result["skip_reason"] in SKIP_REASONS


def test_benchmark_receipt_has_no_synthetic_numbers():
    receipt = get_executor("benchmark")(_plan(), "bench")
    flat = repr(receipt.outcome)
    for token in ("health", "hallucination", "score", "success_rate"):
        assert token not in flat


def test_archived_modules_warn_on_import():
    code = (
        "import importlib, importlib.util, warnings\n"
        "warnings.simplefilter('always')\n"
        f"mods = {sorted(ARCHIVED_MODULES)!r}\n"
        "missing = []\n"
        "for m in mods:\n"
        "    with warnings.catch_warnings(record=True) as w:\n"
        "        warnings.simplefilter('always')\n"
        "        importlib.import_module(m)\n"
        "    if not any('ARCHIVED 2026-10-12' in str(x.message) for x in w):\n"
        "        missing.append(m)\n"
        f"deleted = {sorted(DELETED_MODULES)!r}\n"
        "importable = [m for m in deleted if importlib.util.find_spec(m) is not None]\n"
        "print('MISSING', missing)\n"
        "print('IMPORTABLE', importable)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=180
    )
    assert proc.returncode == 0, proc.stderr
    assert "MISSING []" in proc.stdout, proc.stdout
    assert "IMPORTABLE []" in proc.stdout, proc.stdout


def _imported_modules(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def test_no_live_code_imports_archived_modules():
    archived_files = {ROOT / rel for rel in ARCHIVED_MODULES.values()}
    archived_files |= {
        ROOT / "nexus/federation" / name
        for name in ("__init__.py", "config.py", "node_launcher.py", "node_registry.py")
    } | {ROOT / "nexus/oracle/promote.py"}
    archived_files |= {
        ROOT / "scripts/ops/federated_engine_v09.py",
        ROOT / "scripts/ops/evolution_engine_v08.py",
        ROOT / "scripts/engine/commands/stress_test.py",
        ROOT / "scripts/engine/commands/ui_explorer.py",
    }
    archived = (
        set(ARCHIVED_MODULES)
        | set(DELETED_MODULES)
        | {
            "nexus.federation",
            "nexus.federation.config",
            "nexus.federation.node_launcher",
            "nexus.federation.node_registry",
            "nexus.oracle.promote",
            "scripts.ops.federated_engine_v09",
            "scripts.ops.evolution_engine_v08",
            "scripts.engine.commands.stress_test",
            "scripts.engine.commands.ui_explorer",
        }
    )
    offenders: list[str] = []
    for top in ("nexus", "scripts"):
        for path in (ROOT / top).rglob("*.py"):
            if path in archived_files or "__pycache__" in path.parts:
                continue
            hit = _imported_modules(path) & archived
            if hit:
                offenders.append(f"{path.relative_to(ROOT)}: {sorted(hit)}")
    assert not offenders, offenders


def test_lewm_switch_is_inert_and_latent_switch_is_kept(monkeypatch):
    from nexus.core.state_contracts import NexusState
    from nexus.engine.repair_attempt_service import RepairAttemptService
    from nexus.learning import predictor_toggle

    assert predictor_toggle.env_name(predictor_toggle.LATENT_PREDICTOR) == "NEXUS_LATENT_PREDICTOR"
    entries = []
    for value in ("on", "off"):
        monkeypatch.setenv("NEXUS_LEWM_PREDICTOR", value)
        state = NexusState(task_id="arch-3")
        state.metadata["sim_lewm"] = True
        assert RepairAttemptService(project_root="/tmp/x")._run_lewm_sim(state) is None
        entries.append(state.metadata["predictor_influence"])
    assert entries[0] == entries[1]
    assert entries[0][0]["consulted"] is False


def test_nexus_benchmark_cli_fails_closed():
    from click.testing import CliRunner

    from nexus.cli.commands.core import benchmark

    result = CliRunner().invoke(benchmark, ["--tasks", "1"])
    assert result.exit_code == 1
    assert "archived_fake_benchmark_2026-10-12" in result.output
    assert "Complete" not in result.output
