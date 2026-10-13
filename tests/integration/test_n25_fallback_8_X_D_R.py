import itertools
import time as _real_time

import pytest

from nexus.core import capability_executor_registry as _registry
from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY

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
    # Make elapsed time deterministic so the test proves the executors report a real
    # monotonic delta instead of depending on how fast the machine is.
    monkeypatch.setattr(_registry, "time", _SteppingTime())


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="test-n25", task_id="n25", phases=["X"])


def _test_executor(name: str) -> None:
    fn = EXECUTOR_REGISTRY.get(name)
    assert fn is not None, f"{name} not in registry"
    plan = _plan()
    r = fn(plan, "test task")
    assert r.invoked, f"{name}: invoked={r.invoked}"
    assert r.gate_passed, f"{name}: gate_passed={r.gate_passed}"
    # With the stepping clock every monotonic() call advances STEP_MS, so a genuine
    # start/end measurement yields at least STEP_MS. An executor that hardcodes 0 fails here.
    tel = r.telemetries
    assert tel["telemetry_source"] == "measured", (
        f"{name}: telemetry_source={tel['telemetry_source']}"
    )
    assert isinstance(tel["wall_time_ms"], int), f"{name}: wall_time_ms={tel['wall_time_ms']!r}"
    assert tel["wall_time_ms"] >= STEP_MS, f"{name}: wall_time_ms={tel['wall_time_ms']}"


def _assert_retired(name: str) -> None:
    # Executor-only key with no planner node, archived 2026-10-13 (ARCHIVED_2026-10-13.md, #1906):
    # the historical node id is kept and now asserts the key is unreachable.
    assert name not in EXECUTOR_REGISTRY, f"{name} must not be registered"


def test_exec_learn_refresh_service_runs() -> None:
    _assert_retired("learn_refresh_service")


def test_exec_learn_scheduler_service_runs() -> None:
    _test_executor("learn_scheduler_service")


def test_exec_belief_runs() -> None:
    _test_executor("belief")


def test_exec_autoreason_runs() -> None:
    _test_executor("autoreason")


def test_exec_repair_loop_runs() -> None:
    _test_executor("repair_loop")


def test_exec_hyper_sprint_runs() -> None:
    _test_executor("hyper_sprint")


def test_exec_swarm_multi_agent_runs() -> None:
    _test_executor("swarm_multi_agent")


def test_exec_drone_runs() -> None:
    _test_executor("drone")
