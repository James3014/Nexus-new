"""The learn_scheduler gate reads its report from the process store, never from context (#2829).

``learn_scheduler_service`` gates on ``slo_readiness`` from
``<store>/.nexus/reports/learn/scheduler_last_run.json``.  If the main-chain invoker
passed a request-context ``workspace_root`` into its plan, the caller would choose the
report the gate reads, e.g. a candidate-writable directory holding a passing report.
The invoker therefore allowlists no constraints for ``learn_scheduler`` (as #2826 did for
``learn_mode`` / ``learn_phase_slo``), and the executor resolves the store from the
process: the state root on the live layout, else the cwd.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.state_root import CANONICAL_SOURCE_ROOT_ENV, STATE_ROOT_ENV

REPORT = Path(".nexus/reports/learn/scheduler_last_run.json")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (STATE_ROOT_ENV, CANONICAL_SOURCE_ROOT_ENV, "NEXUS_TARGET_ROOT_OVERRIDE"):
        monkeypatch.delenv(name, raising=False)


def _write_report(root: Path, readiness: float) -> None:
    path = root / REPORT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"slo_readiness": readiness}), encoding="utf-8")


def _forged_context(attacker: Path) -> dict[str, Any]:
    return {
        "task_id": "t-2829",
        "task_statement": "s",
        "workspace_root": str(attacker),
        "project_root": str(attacker),
        "route": {"workspace_root": str(attacker)},
        "codeintel": {"workspace_root": str(attacker)},
    }


def test_invoker_passes_no_context_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.core.capability_executor_registry as cer
    from nexus.services.capability_registry import build_real_executor_invoker

    seen: list[CapabilityExecutionPlan] = []

    def fake_executor(plan: CapabilityExecutionPlan, statement: str) -> dict[str, Any]:
        seen.append(plan)
        return {"status": "OK"}

    monkeypatch.setattr(cer, "get_executor", lambda key: fake_executor)
    invoker = build_real_executor_invoker("learn_scheduler")
    assert invoker is not None
    invoker(_forged_context(tmp_path / "target"))
    assert len(seen) == 1
    assert not seen[0].constraints


class _FakeScheduler:
    """Stands in for LearnSchedulerService: records the store, writes nothing."""

    roots: list[Path] = []

    def __init__(self, *, repo_root: Path, report_root: Path, project_root: Path) -> None:
        type(self).roots.append(report_root)

    def run_scheduler(self) -> int:
        return 0


def test_end_to_end_forged_passing_report_does_not_flip_the_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoker -> real learn_scheduler executor on the live layout: a passing report at a
    context-chosen root is never read; the gate uses the state root's failing report."""
    import nexus.core.capability_executor_registry as cer
    from nexus.services.capability_registry import build_real_executor_invoker

    state = tmp_path / "state"
    controller = tmp_path / "controllers" / "a1-x"
    controller.mkdir(parents=True)
    attacker = tmp_path / "target"
    _write_report(state, 0.1)
    _write_report(attacker, 1.0)
    monkeypatch.setenv(STATE_ROOT_ENV, str(state))
    monkeypatch.setenv(CANONICAL_SOURCE_ROOT_ENV, str(controller))
    monkeypatch.chdir(controller)
    _FakeScheduler.roots = []
    monkeypatch.setattr(
        cer,
        "_try_port",
        lambda name: _FakeScheduler if name == "learn_scheduler.LearnSchedulerService" else None,
    )
    invoker = build_real_executor_invoker("learn_scheduler")
    assert invoker is not None
    result = invoker(_forged_context(attacker))
    dumped = json.dumps(result, default=str)
    assert _FakeScheduler.roots == [state.resolve()]
    assert str(state.resolve()) in dumped
    assert str(attacker) not in dumped
    assert "BLOCKED" in dumped


def test_without_state_root_the_cwd_is_the_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nexus.core.capability_executor_registry as cer

    _write_report(tmp_path, 0.9)
    monkeypatch.chdir(tmp_path)
    _FakeScheduler.roots = []
    monkeypatch.setattr(cer, "_try_port", lambda name: _FakeScheduler)
    plan = CapabilityExecutionPlan(plan_id="p", task_id="t", phases=["R"], constraints={})
    receipt = cer.EXECUTOR_REGISTRY["learn_scheduler_service"](plan, "schedule")
    assert _FakeScheduler.roots == [tmp_path.resolve()]
    assert receipt.gate_passed is True
