"""Second-batch archive (2026-10-13, #1906): retired capabilities are unreachable, visibly."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY, get_executor
from nexus.services.capability_registry import (
    ARCHIVED_CAPABILITY_REASONS,
    SKIP_REASONS,
    build_default_mainchain_invokers,
    list_planner_capability_names,
)

ROOT = Path(__file__).resolve().parents[2]

# Planner nodes whose definitions live in the pinned nexus-runtime; the runtime maturity
# flip rides the next runtime PR, so the Nexus side resolves them to explicit reasons.
PLANNER_NODE_REASONS = {
    "integration_manager": "archived_retired_integration_manager_2026-10-13",
    "swarm_quiet_moment": "archived_echo_swarm_quiet_moment_2026-10-13",
    "llm_judge_panel": "archived_alias_llm_judge_panel_2026-10-13",
}

# Executor-registry keys with no planner node.  entropy_guard_v2 left this list with the
# runtime 68e86ed pin, which defines its planner node (nexus-runtime #198, #1907).
RETIRED_EXECUTOR_KEYS = (
    "policy_capability_gate",
    "aos_oracle",
    "learn_refresh_service",
    "zero_trust_v2_behavior",
    "predictive_auditor",
    "spec_guarded",
    "decision_formula_engine",
    "reflex_loop",
    "dual_loop",
    "mfp_gate",
    "promotion_engine",
    "subagent_outcome_service",
    "attempt_settlement_service",
    "battle_swarm",
    "nightshift_runner_service",
    "research_and_source_discipline",
)

ARCHIVED_MODULES = {
    "nexus.cli.commands.core": "nexus/cli/commands/core.py",
    "nexus.cli.commands.guard": "nexus/cli/commands/guard.py",
    "nexus.cli.commands.healing": "nexus/cli/commands/healing.py",
    "nexus.cli.commands.health": "nexus/cli/commands/health.py",
    "nexus.cli.commands.memory": "nexus/cli/commands/memory.py",
    "nexus.cli.commands.swarm": "nexus/cli/commands/swarm.py",
    "nexus.cli.commands.swarm_v2": "nexus/cli/commands/swarm_v2.py",
    "nexus.cli.commands.wisdom": "nexus/cli/commands/wisdom.py",
    "nexus.research.learn.claim_service": "nexus/research/learn/claim_service.py",
    "nexus.core.web_dom_mapper": "nexus/core/web_dom_mapper.py",
    "nexus.core.web_action_executor": "nexus/core/web_action_executor.py",
    "nexus.engine.replay_runner": "nexus/engine/replay_runner.py",
    "nexus.core.planner_auditor": "nexus/core/planner_auditor.py",
    "nexus.core.capability_gate": "nexus/core/capability_gate.py",
    "nexus.orchestrator.integration_manager": "nexus/orchestrator/integration_manager.py",
}

# Archived here first, then physically deleted 2026-10-17 (#2491, dead-code batch B3,
# ARCHIVED_2026-10-17_deadcode_b3.md): no longer importable at all.
DELETED_MODULES = {
    "nexus.services.local_heal.linear_replay_runner": (
        "nexus/services/local_heal/linear_replay_runner.py"
    ),
}

# Already-archived first-batch files that still import a second-batch module.
FIRST_BATCH_ARCHIVED_IMPORTERS = {"scripts/ui-validator.py"}


def _plan(task_id: str = "arch2-1") -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id=f"plan-{task_id}", task_id=task_id, phases=["R"], constraints={}
    )


def test_reason_table_and_whitelist():
    for name, reason in PLANNER_NODE_REASONS.items():
        assert ARCHIVED_CAPABILITY_REASONS[name] == reason
        assert reason in SKIP_REASONS


@pytest.mark.parametrize("name", sorted(PLANNER_NODE_REASONS))
def test_planner_node_executor_emits_archived_reason(name):
    executor = get_executor(name)
    assert executor is not None, "archived planner node keeps an archived executor"
    receipt = executor(_plan(), "any task")
    reason = PLANNER_NODE_REASONS[name]
    assert receipt.capability_name == name
    assert receipt.invoked is False
    assert receipt.gate_passed is False
    assert receipt.outcome["skip_reason"] == reason
    assert receipt.outcome["semantic_status"] == "BLOCKED"
    assert receipt.outcome["archived"] is True


@pytest.mark.parametrize("name", sorted(PLANNER_NODE_REASONS))
def test_planner_node_resolves_to_archived_skip(name):
    assert name in set(list_planner_capability_names()), "runtime still defines the node"
    invokers = build_default_mainchain_invokers()
    result = invokers[name]({"task_id": "arch2-2", "escalate_triggered": True})
    assert result["skipped"] is True
    assert result["invoked"] is False
    assert result["skip_reason"] == PLANNER_NODE_REASONS[name]


# Keys that left the executor-only list keep their node id here and assert the new contract.
PROMOTED_EXECUTOR_KEYS = ("entropy_guard_v2",)


@pytest.mark.parametrize("key", RETIRED_EXECUTOR_KEYS + PROMOTED_EXECUTOR_KEYS)
def test_executor_only_key_is_not_registered(key):
    if key in PROMOTED_EXECUTOR_KEYS:
        # entropy_guard_v2 is no longer an executor-only key: the 68e86ed runtime defines its
        # planner node and Nexus-new registers the executor for it (#1907).
        assert key in set(list_planner_capability_names())
        assert get_executor(key) is EXECUTOR_REGISTRY[key]
        return
    assert key not in EXECUTOR_REGISTRY
    assert get_executor(key) is None


def test_kept_surfaces_behind_retired_keys_still_work():
    import nexus.core.capability_executor_registry as reg

    # nightshift keeps its executor body; only the alias key went away.
    assert EXECUTOR_REGISTRY["nightshift"] is reg._exec_nightshift
    assert callable(reg._exec_nightshift_runner_service)
    # swarm / multi_agent keep the real executor that battle_swarm aliased.
    assert EXECUTOR_REGISTRY["swarm_multi_agent"] is reg._exec_swarm_multi_agent
    # policy_gate (legacy self_heal_selector) and entropy_v2 (#1907) modules are kept.
    from nexus.services.entropy_v2 import EntropyGuardV2
    from nexus.services.policy_gate import apply_policy_gate

    assert callable(apply_policy_gate) and EntropyGuardV2 is not None


def test_archived_modules_warn_on_import():
    code = (
        "import importlib, importlib.util, warnings\n"
        f"mods = {sorted(ARCHIVED_MODULES)!r}\n"
        "missing = []\n"
        "for m in mods:\n"
        "    with warnings.catch_warnings(record=True) as w:\n"
        "        warnings.simplefilter('always')\n"
        "        importlib.import_module(m)\n"
        "    if not any('ARCHIVED 2026-10-13' in str(x.message) for x in w):\n"
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
    allowed = {ROOT / rel for rel in ARCHIVED_MODULES.values()}
    allowed |= {ROOT / rel for rel in FIRST_BATCH_ARCHIVED_IMPORTERS}
    archived = set(ARCHIVED_MODULES) | set(DELETED_MODULES)
    offenders: list[str] = []
    for top in ("nexus", "scripts"):
        for path in (ROOT / top).rglob("*.py"):
            if path in allowed or "__pycache__" in path.parts:
                continue
            hit = _imported_modules(path) & archived
            if hit:
                offenders.append(f"{path.relative_to(ROOT)}: {sorted(hit)}")
    assert not offenders, offenders


def test_retired_cli_commands_are_gone():
    import scripts.engine.nexus_cli as cli_mod

    runner = CliRunner()
    for args in (
        ["nexus", "delegate", "task"],
        ["nexus", "multi-agent", "integrate", "--task-ids", "A"],
        ["nexus", "swarm", "quiet-moment", "--reason", "x"],
    ):
        result = runner.invoke(cli_mod.nexus, args)
        assert result.exit_code == 2, (args, result.output)
        assert "No such command" in result.output, args


def test_learn_mode_no_longer_constructs_claim_service(tmp_path):
    from nexus.research.learn_mode import LearnModeService

    assert not hasattr(LearnModeService(tmp_path), "_claim_svc")
    source = (ROOT / "nexus/research/learn_mode.py").read_text(encoding="utf-8")
    assert "ClaimService" not in source


def test_nexus_fs_router_bias_no_longer_reads_federated_dna(tmp_path, monkeypatch):
    from nexus.services import mem_palace
    from nexus.services.nexus_fs import NexusFS, PathNode

    def _boom(self):  # pragma: no cover - must not be reached
        raise AssertionError("router_bias display must not read configs/federated_dna.yaml")

    monkeypatch.setattr(mem_palace.MemPalace, "get_router_bias", _boom)
    fs = NexusFS.__new__(NexusFS)
    fs.project_root = tmp_path
    node = PathNode("router_bias", is_dir=False, content_provider="belief")
    payload = json.loads(fs._handle_belief_cat("/virtual/router_bias", node))
    assert payload["global_router_bias"] == "n/a"
    assert payload["reason"] == "archived_federated_dna_2026-10-13"
