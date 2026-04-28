from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from nexus.engine.pipeline_repair import PipelineRepairMixin


class DummyTracer:
    def phase_span(self, *_args, **_kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class DummyRepairEngine(PipelineRepairMixin):
    def __init__(self, project_root: Path):
        self.engine = self
        self.project_root = project_root
        self.max_retries = 2
        self._check_external_interrupt = MagicMock(return_value=False)
        self._add_step_to_history = MagicMock()


def _ctx(*, enabled: bool = False, budget: dict[str, int] | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.task_id = "rlm submit handoff"
    ctx.task_desc = "repair with recursive trace"
    ctx.dry_run = False
    ctx.pack = {}
    ctx.state = MagicMock()
    ctx.state.task_id = ctx.task_id
    ctx.state.retry_count = 0
    ctx.state.current_phase = ""
    ctx.state.metadata = {}
    if enabled:
        ctx.state.metadata["rlm_recursive_repair_enabled"] = True
    if budget is not None:
        ctx.state.metadata["rlm_budget"] = budget
    return ctx


def _approved_repair() -> dict[str, object]:
    return {
        "status": "APPROVED",
        "result": {"patch_generated": True, "patch_apply_success": True},
        "current_decision_id": "r-decision",
        "current_skill_id": "repair-skill",
    }


def _trace_events(project_root: Path, task_slug: str = "rlm-submit-handoff") -> list[dict[str, object]]:
    trace_path = project_root / ".nexus" / "reports" / "rlm_trace" / f"{task_slug}.jsonl"
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]


def test_recursive_repair_default_off_preserves_existing_loop(tmp_path: Path):
    engine = DummyRepairEngine(tmp_path)
    engine._execute_single_repair = MagicMock(return_value=_approved_repair())
    engine._evaluate_audit_result = MagicMock(
        return_value={"audit_success": True, "status": "APPROVED", "phantom_reason": None}
    )

    assert engine._repair_audit_loop(_ctx(), DummyTracer()) is True

    assert not (tmp_path / ".nexus" / "reports" / "rlm_trace").exists()
    engine._execute_single_repair.assert_called_once()
    engine._evaluate_audit_result.assert_called_once()


def test_recursive_repair_traces_submit_but_a_gate_decides_success(tmp_path: Path):
    engine = DummyRepairEngine(tmp_path)
    engine._execute_single_repair = MagicMock(return_value=_approved_repair())
    engine._evaluate_audit_result = MagicMock(
        return_value={"audit_success": False, "status": "REJECTED", "phantom_reason": "missing_evidence"}
    )
    engine._handle_escalation = MagicMock(return_value=(True, False))
    ctx = _ctx(enabled=True)

    assert engine._repair_audit_loop(ctx, DummyTracer()) is False

    events = _trace_events(tmp_path)
    assert [event["phase"] for event in events] == ["R", "A"]
    assert events[0]["action_type"] == "submit"
    assert events[0]["stop_reason"] == "submit"
    assert events[1]["action_type"] == "audit"
    assert events[1]["stop_reason"] == "audit_rejected"
    assert ctx.state.metadata["rlm_recursive_trace_path"].endswith("rlm-submit-handoff.jsonl")


def test_recursive_repair_budget_exhaustion_fails_closed(tmp_path: Path):
    engine = DummyRepairEngine(tmp_path)
    engine._execute_single_repair = MagicMock(return_value=_approved_repair())
    engine._evaluate_audit_result = MagicMock(
        return_value={"audit_success": False, "status": "REJECTED", "phantom_reason": None}
    )
    engine._handle_escalation = MagicMock(return_value=(False, False))
    ctx = _ctx(enabled=True, budget={"max_iterations": 1})

    assert engine._repair_audit_loop(ctx, DummyTracer()) is False

    events = _trace_events(tmp_path)
    assert [event["stop_reason"] for event in events] == ["submit", "audit_rejected", "budget_exhausted"]
    assert ctx.state.metadata["rlm_budget_exhausted"] is True
    assert ctx.state.metadata["rlm_budget_exhausted_reasons"] == ["max_iterations"]
    engine._execute_single_repair.assert_called_once()
