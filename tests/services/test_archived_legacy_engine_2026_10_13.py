"""Legacy-engine archive (2026-10-13): the legacy NexusEngine is unreachable, visibly.

See ARCHIVED_2026-10-13-legacy-engine.md. ``execute_canonical_product_task`` is the only
product entry; the legacy NexusEngine / CommandService builders fail closed, the planner node
``autonomic_router`` resolves to an archived receipt, and every archived module warns on import.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import get_executor
from nexus.services.capability_registry import (
    ARCHIVED_CAPABILITY_REASONS,
    SKIP_REASONS,
    build_default_mainchain_invokers,
    list_planner_capability_names,
)

ROOT = Path(__file__).resolve().parents[2]
WARNING_TAG = "ARCHIVED 2026-10-13 legacy-engine"
AUTONOMIC_ROUTER_REASON = "archived_legacy_engine_autonomic_router_2026-10-13"

ARCHIVED_MODULES = {
    "nexus.engine.coordinator": "nexus/engine/coordinator.py",
    "nexus.engine.bootstrap": "nexus/engine/bootstrap.py",
    "nexus.engine.pipeline": "nexus/engine/pipeline.py",
    "nexus.engine.pipeline_stages": "nexus/engine/pipeline_stages.py",
    "nexus.engine.pipeline_repair": "nexus/engine/pipeline_repair.py",
    "nexus.engine.recursive_repair_loop": "nexus/engine/recursive_repair_loop.py",
    "nexus.engine.autonomic_router": "nexus/engine/autonomic_router.py",
    "nexus.engine.autonomic_routing_service": "nexus/engine/autonomic_routing_service.py",
    "nexus.engine.repair_setup_service": "nexus/engine/repair_setup_service.py",
    "nexus.engine.cli_runner_async": "nexus/engine/cli_runner_async.py",
    "nexus.app.command_service": "nexus/app/command_service.py",
    "nexus.evaluation.eval_harness": "nexus/evaluation/eval_harness.py",
    "nexus.benchmark.benchmark_runner": "nexus/benchmark/benchmark_runner.py",
    "nexus.services.cli_commands_service": "nexus/services/cli_commands_service.py",
    "scripts.engine.commands.swarm": "scripts/engine/commands/swarm.py",
    "scripts.ci.run_smoke_benchmark": "scripts/ci/run_smoke_benchmark.py",
}

# Modules that still import an archived module but are themselves reachable only through the
# legacy engine (or are manual lab scripts); listed in the manifest for the deletion PR.
LEGACY_ONLY_IMPORTERS = {
    "nexus/containers.py",  # unimportable: dependency_injector is not a declared dependency
    "nexus/cli/utils.py",  # lazy import in _get_service, used only by the archived nexus/cli/commands
    "scripts/tests/test_v4_intelligence.py",  # ad-hoc script under scripts/ (not collected by pytest)
    "nexus/learning/router_nas_tuner.py",  # only importer: nexus/engine/reflex_loop.py (bootstrap)
    "scripts/ops/router_policy_benchmark.py",  # manual benchmark script, no caller
    "scripts/scratch/phase13_acceptance.py",
    "scripts/scratch/phase13_closed_loop_test.py",
}

PRODUCTION_ENTRIES = (
    "scripts.engine.nexus_cli",
    "nexus.engine.canonical_task_seam",
    "nexus.core.capability_executor_registry",
    "nexus.services.capability_registry",
    "nexus.orchestrator.unified_mcp_gateway",
    "nexus.orchestrator.self_hosted_task_service",
)


def _plan(task_id: str = "legacy-engine-1") -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id=f"plan-{task_id}", task_id=task_id, phases=["P"], constraints={}
    )


def test_autonomic_router_reason_is_receipt_visible():
    assert ARCHIVED_CAPABILITY_REASONS["autonomic_router"] == AUTONOMIC_ROUTER_REASON
    assert AUTONOMIC_ROUTER_REASON in SKIP_REASONS


def test_autonomic_router_executor_emits_archived_receipt():
    executor = get_executor("autonomic_router")
    assert executor is not None, "the planner node keeps an archived executor"
    receipt = executor(_plan(), "Route the refund change")
    assert receipt.invoked is False
    assert receipt.gate_passed is False
    assert receipt.outcome["skip_reason"] == AUTONOMIC_ROUTER_REASON
    assert receipt.outcome["semantic_status"] == "BLOCKED"
    assert receipt.outcome["archived"] is True


def test_autonomic_router_planner_node_resolves_to_archived_skip():
    assert "autonomic_router" in set(list_planner_capability_names())
    invokers = build_default_mainchain_invokers()
    result = invokers["autonomic_router"]({
        "task_id": "legacy-engine-2",
        "escalate_triggered": True,
    })
    assert result["skipped"] is True
    assert result["invoked"] is False
    assert result["skip_reason"] == AUTONOMIC_ROUTER_REASON


def test_autonomic_router_port_is_unbound():
    from nexus.engine.core_ports import CORE_ENGINE_PORTS

    assert "autonomic_router.AutonomicRouter" not in CORE_ENGINE_PORTS
    source = (ROOT / "nexus/core/capability_executor_registry.py").read_text(encoding="utf-8")
    assert '_try_port("autonomic_router.AutonomicRouter")' not in source


@pytest.mark.parametrize(
    "entry",
    [
        "build_engine",
        "build_command_service",
        "build_legacy_cli_service",
        "execute_single_task_via_service",
    ],
)
def test_seam_legacy_builders_fail_closed(entry, tmp_path):
    import nexus.engine.canonical_task_seam as seam

    func = getattr(seam, entry)
    args = ("fix bug", tmp_path) if entry == "execute_single_task_via_service" else (tmp_path,)
    with pytest.raises(seam.LegacyEngineArchivedError) as excinfo:
        func(*args)
    assert excinfo.value.entry == entry
    assert excinfo.value.reason == "archived_legacy_engine_2026-10-13"
    assert WARNING_TAG in str(excinfo.value)
    source = (ROOT / "nexus/engine/canonical_task_seam.py").read_text(encoding="utf-8")
    assert "nexus.engine.coordinator" not in source
    assert "app.command_service" not in source


def test_archived_modules_warn_on_import():
    # One interpreter: archived modules import each other, so a module may first load (and
    # warn) as a dependency of another; every warning names its own module.
    code = (
        "import importlib, warnings\n"
        f"mods = {sorted(ARCHIVED_MODULES)!r}\n"
        "with warnings.catch_warnings(record=True) as w:\n"
        "    warnings.simplefilter('always')\n"
        "    for m in mods:\n"
        "        importlib.import_module(m)\n"
        f"text = [str(x.message) for x in w if {WARNING_TAG!r} in str(x.message)]\n"
        "missing = [m for m in mods if not any(m + ' ' in t for t in text)]\n"
        "print('MISSING', missing)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr
    assert "MISSING []" in proc.stdout, proc.stdout


def test_production_entries_do_not_load_archived_modules():
    code = (
        "import importlib, sys, warnings\n"
        "warnings.simplefilter('always')\n"
        f"for m in {list(PRODUCTION_ENTRIES)!r}:\n"
        "    importlib.import_module(m)\n"
        f"loaded = sorted(set({sorted(ARCHIVED_MODULES)!r}) & set(sys.modules))\n"
        "print('LOADED', loaded)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300
    )
    assert proc.returncode == 0, proc.stderr
    assert "LOADED []" in proc.stdout, proc.stdout
    assert WARNING_TAG not in proc.stderr


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
    allowed = {ROOT / rel for rel in ARCHIVED_MODULES.values()}
    allowed |= {ROOT / rel for rel in LEGACY_ONLY_IMPORTERS}
    archived = set(ARCHIVED_MODULES)
    offenders: list[str] = []
    for top in ("nexus", "scripts"):
        for path in (ROOT / top).rglob("*.py"):
            if path in allowed or "__pycache__" in path.parts:
                continue
            hit = _imported_modules(path) & archived
            if hit:
                offenders.append(f"{path.relative_to(ROOT)}: {sorted(hit)}")
    assert not offenders, offenders


def test_legacy_swarm_run_command_is_gone():
    import scripts.engine.nexus_cli as cli_mod

    result = CliRunner().invoke(cli_mod.nexus, ["nexus", "swarm", "run", "fix typo"])
    assert result.exit_code == 2, result.output
    assert "No such command" in result.output


def test_nexus_cli_shim_fails_closed(tmp_path):
    import scripts.engine.nexus_cli as cli_mod
    from nexus.engine.canonical_task_seam import LegacyEngineArchivedError

    with pytest.raises(LegacyEngineArchivedError):
        cli_mod.NexusCLI(project_root=tmp_path)


def test_smoke_benchmark_script_refuses_and_workflow_is_manual_only(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/run_smoke_benchmark.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert WARNING_TAG in proc.stderr
    assert not (tmp_path / ".nexus" / "reports").exists()
    doc = yaml.safe_load((ROOT / ".github/workflows/nexus-smoke.yml").read_text(encoding="utf-8"))
    triggers = doc.get("on", doc.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    run_lines = []
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        wf = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in (wf.get("jobs") or {}).values():
            run_lines.extend(str(step.get("run") or "") for step in job.get("steps") or [])
    assert not [line for line in run_lines if "run_smoke_benchmark.py" in line]
