import itertools
import time as _real_time

import pytest

from nexus.core import capability_executor_registry as _registry
from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
from nexus.core.belief_contracts import CapabilityExecutionPlan

STEP_MS = 5


class _SteppingTime:
    """Proxy for the registry's `time` module whose monotonic() advances STEP_MS per call."""

    def __init__(self) -> None:
        self._ticks = itertools.count()

    def monotonic(self) -> float:
        return next(self._ticks) * STEP_MS / 1000.0

    def __getattr__(self, name: str):
        return getattr(_real_time, name)


@pytest.fixture(autouse=True)
def _deterministic_clock(monkeypatch):
    # Deterministic elapsed time: proves executors report a real monotonic delta
    # instead of depending on how fast the machine is (wall_time_ms=0 flake).
    monkeypatch.setattr(_registry, "time", _SteppingTime())


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="test-n24", task_id="n24", phases=["S"])


def _test_executor(name: str) -> None:
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed, f"{name}: gate_passed={r.gate_passed}"
    tel = r.telemetries
    assert tel["telemetry_source"] == "measured", f"{name}: telemetry_source={tel['telemetry_source']}"
    assert isinstance(tel["wall_time_ms"], int), f"{name}: wall_time_ms={tel['wall_time_ms']!r}"
    assert tel["wall_time_ms"] >= STEP_MS, f"{name}: wall_time_ms={tel['wall_time_ms']}"


def _assert_fail_closed(
    name: str,
    error: str,
    *,
    status: str | None = "BLOCKED",
    invoked: bool = True,
) -> None:
    # Stub success was removed on purpose (99c8295ba, 13df4578d, 7ae787b81; #1850 archive):
    # the executor now fails closed and reports the specific reason below.
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked is invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed is False, f"{name}: gate_passed={r.gate_passed}"
    assert r.outcome.get("semantic_status") == status, f"{name}: {r.outcome}"
    assert r.outcome.get("error") == error, f"{name}: {r.outcome}"


def _assert_retired(name: str) -> None:
    # Executor-only key with no planner node, archived 2026-10-13 (ARCHIVED_2026-10-13.md, #1906):
    # the historical node id is kept and now asserts the key is unreachable.
    assert name not in EXECUTOR_REGISTRY, f"{name} must not be registered"


def test_exec_policy_capability_gate_runs() -> None:
    _assert_retired("policy_capability_gate")


def test_exec_nightshift_runner_service_runs() -> None:
    _assert_retired("nightshift_runner_service")


def test_exec_decision_formula_engine_runs() -> None:
    _assert_retired("decision_formula_engine")


def test_exec_codeintel_runs() -> None:
    _assert_fail_closed("codeintel", "TARGET_SYMBOL_REQUIRED")


def test_exec_lancedb_runs() -> None:
    _test_executor("lancedb")


def test_exec_research_runs() -> None:
    _assert_fail_closed("research", "BLOCKED_EXTERNAL_AUTH")


def test_exec_research_and_source_discipline_runs() -> None:
    _assert_retired("research_and_source_discipline")
