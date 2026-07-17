"""RC-3: _make_receipt must not invent measured wall/tokens."""
from __future__ import annotations

from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.core.capability_executor_registry import _honest_structural_telemetries, _make_receipt


def _plan() -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(plan_id="p", task_id="t")


def test_make_receipt_default_wall_is_unavailable_not_measured():
    r = _make_receipt("codeintel", _plan(), invoked=True, gate_passed=True)
    t = r.telemetries
    assert t.get("telemetry_source") == "unavailable"
    assert t.get("wall_time_ms") is None
    assert t.get("token_usage") is None
    assert t.get("claimable") is False
    assert r.is_claimable is False


def test_make_receipt_with_real_elapsed_is_measured():
    r = _make_receipt("codeintel", _plan(), wall_time_ms=42)
    t = r.telemetries
    assert t.get("telemetry_source") == "measured"
    assert t.get("wall_time_ms") == 42
    assert t.get("model_calls") == 0
    # still not public-claimable by structural path alone
    assert t.get("claimable") is False


def test_honest_helper_rejects_measured_without_wall():
    t = _honest_structural_telemetries(None, extra={"telemetry_source": "measured"})
    assert t.get("telemetry_source") == "unavailable"
    assert t.get("wall_time_ms") is None
