"""The learn store comes from the process, never from the task context (#2826).

``learn_phase_slo`` fails closed (#2715).  If the main-chain invoker passed request
context (``workspace_root``, ``run_root``) into its plan, the caller would choose which
ledger the gate reads, e.g. a candidate-writable ``<target>/.nexus``.  The invoker
therefore allowlists no constraints for ``learn_mode`` / ``learn_phase_slo``, and the
store resolves from the process: the state root on the live layout, else the cwd.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.state_root import CANONICAL_SOURCE_ROOT_ENV, STATE_ROOT_ENV

LEARN_CAPABILITIES = ("learn_mode", "learn_phase_slo")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (STATE_ROOT_ENV, CANONICAL_SOURCE_ROOT_ENV, "NEXUS_TARGET_ROOT_OVERRIDE"):
        monkeypatch.delenv(name, raising=False)


def _captured_plan(monkeypatch: pytest.MonkeyPatch, capability: str, context: dict[str, Any]):
    import nexus.core.capability_executor_registry as cer
    from nexus.services.capability_registry import build_real_executor_invoker

    seen: list[CapabilityExecutionPlan] = []

    def fake_executor(plan: CapabilityExecutionPlan, statement: str) -> dict[str, Any]:
        seen.append(plan)
        return {"status": "OK"}

    monkeypatch.setattr(cer, "get_executor", lambda key: fake_executor)
    invoker = build_real_executor_invoker(capability)
    assert invoker is not None
    invoker(context)
    assert len(seen) == 1
    return seen[0]


@pytest.mark.parametrize("capability", LEARN_CAPABILITIES)
def test_invoker_passes_no_context_constraints(
    capability: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attacker = tmp_path / "target"
    context = {
        "task_id": "t-2826",
        "task_statement": "s",
        "workspace_root": str(attacker),
        "project_root": str(attacker),
        "run_root": str(attacker),
        "runtime_root": str(attacker),
        "run_id": "forged",
        "route": {"workspace_root": str(attacker)},
    }
    plan = _captured_plan(monkeypatch, capability, context)
    assert not plan.constraints


def test_live_layout_resolves_to_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Like the live launchd command: cwd = NEXUS_CANONICAL_SOURCE_ROOT, state root set."""
    from nexus.core.capability_executor_registry import _resolve_learn_store

    state = tmp_path / "state"
    state.mkdir()
    controller = tmp_path / "controllers" / "a1-x"
    controller.mkdir(parents=True)
    monkeypatch.setenv(STATE_ROOT_ENV, str(state))
    monkeypatch.setenv(CANONICAL_SOURCE_ROOT_ENV, str(controller))
    monkeypatch.chdir(controller)
    plan = CapabilityExecutionPlan(plan_id="p", task_id="t-2826", phases=["R"], constraints={})
    project_root, run_root, run_id = _resolve_learn_store(plan)
    assert project_root == controller.resolve()
    assert run_root == state.resolve()
    assert run_id == "t-2826"


def test_without_state_root_the_cwd_is_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.core.capability_executor_registry import _resolve_learn_store

    monkeypatch.chdir(tmp_path)
    plan = CapabilityExecutionPlan(plan_id="p", task_id="t", phases=["R"], constraints={})
    project_root, run_root, _ = _resolve_learn_store(plan)
    assert project_root == tmp_path.resolve()
    assert Path(run_root).resolve() == tmp_path.resolve()


def test_end_to_end_gate_reads_state_root_not_forged_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoker -> real learn_phase_slo executor on the live layout: a forged ledger at a
    context-chosen root is never the store the gate reads."""
    import json

    from nexus.services.capability_registry import build_real_executor_invoker

    state = tmp_path / "state"
    state.mkdir()
    controller = tmp_path / "controllers" / "a1-x"
    controller.mkdir(parents=True)
    attacker = tmp_path / "target"
    (attacker / ".nexus").mkdir(parents=True)
    monkeypatch.setenv(STATE_ROOT_ENV, str(state))
    monkeypatch.setenv(CANONICAL_SOURCE_ROOT_ENV, str(controller))
    monkeypatch.chdir(controller)
    invoker = build_real_executor_invoker("learn_phase_slo")
    assert invoker is not None
    result = invoker({
        "task_id": "t-2826-e2e",
        "task_statement": "s",
        "workspace_root": str(attacker),
        "run_root": str(attacker),
        "route": {"workspace_root": str(attacker)},
    })
    dumped = json.dumps(result, default=str)
    assert str(state.resolve()) in dumped
    assert str(attacker) not in dumped
    assert not (attacker / ".nexus" / "reports").exists()
