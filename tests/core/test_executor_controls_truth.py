from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from nexus.core import capability_executor_registry as executor_registry
from nexus.core import executor_controls as controls_module
from nexus.core.belief_contracts import (
    CapabilityExecutionPlan,
    CapabilityReceipt,
    SkillReceipt,
    SkillSlot,
)
from nexus.core.executor_controls import ExecutorControls


class _Registry:
    def __init__(self, phase: str = "P") -> None:
        self.phase = phase

    def get_capability(self, _cap_name: str):
        return SimpleNamespace(phases=[self.phase])


def _plan(
    cap_name: str = "decision_formula_engine",
    *,
    phase: str = "P",
    slots: list[SkillSlot] | None = None,
) -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id="plan-488",
        task_id="task-488",
        phases=[phase],
        required_capabilities=[cap_name],
        skill_slots={cap_name: list(slots or [])},
        constraints={},
    )


def _non_invoked_executor(plan: CapabilityExecutionPlan, _task_desc: str) -> CapabilityReceipt:
    return CapabilityReceipt(
        capability_name=plan.required_capabilities[0],
        selected=True,
        invoked=False,
        evidence_id="ev_real_non_invocation",
        gate_passed=False,
        outcome={"error": "physical_action_not_performed"},
        telemetries={"telemetry_source": "unavailable", "claimable": False},
    )


def test_real_non_invocation_is_preserved(monkeypatch, tmp_path):
    monkeypatch.setattr(controls_module, "get_executor", lambda _name: _non_invoked_executor)

    receipt = ExecutorControls(str(tmp_path), registry=_Registry()).execute_plan(_plan())[0]

    assert receipt.selected is True
    assert receipt.invoked is False
    assert receipt.gate_passed is False
    assert receipt.evidence_id == "ev_real_non_invocation"
    assert receipt.outcome["error"] == "physical_action_not_performed"
    assert receipt.telemetries["telemetry_source"] == "unavailable"


def test_shallow_registry_guard_cannot_be_upgraded_to_invoked(monkeypatch, tmp_path):
    def shallow_executor(plan: CapabilityExecutionPlan, _task_desc: str) -> CapabilityReceipt:
        return executor_registry._make_receipt(  # noqa: SLF001 - regression witness for current guard
            "decision_formula_engine",
            plan,
            outcome={"class_instantiated": True},
        )

    monkeypatch.setattr(controls_module, "get_executor", lambda _name: shallow_executor)

    receipt = ExecutorControls(str(tmp_path), registry=_Registry()).execute_plan(_plan())[0]

    assert receipt.invoked is False
    assert receipt.gate_passed is False
    assert receipt.outcome["error"] == "import_construct_not_execution"


def test_missing_executor_fails_closed_and_selected_skill_is_not_used(monkeypatch, tmp_path):
    monkeypatch.setattr(controls_module, "get_executor", lambda _name: None)
    slot = SkillSlot(role="SCOUT", skill_id="issue-488-scout")

    receipt = ExecutorControls(str(tmp_path), registry=_Registry()).execute_plan(
        _plan(slots=[slot])
    )[0]

    assert receipt.invoked is False
    assert receipt.gate_passed is False
    assert receipt.outcome["error"] == "executor_missing"
    assert receipt.telemetries["telemetry_source"] == "unavailable"
    assert len(receipt.skill_receipts) == 1
    skill_receipt = receipt.skill_receipts[0]
    assert skill_receipt.selected is True
    assert skill_receipt.used is False
    assert skill_receipt.outcome["execution_state"] == "NOT_EXECUTED"
    assert skill_receipt.outcome["reason"] == "skill_use_not_evidenced"


def test_executor_exception_fails_closed_without_persisting_exception_text(monkeypatch, tmp_path):
    secret_marker = "provider-token=do-not-persist"

    def exploding_executor(_plan, _task_desc):
        raise RuntimeError(secret_marker)

    monkeypatch.setattr(controls_module, "get_executor", lambda _name: exploding_executor)

    receipt = ExecutorControls(str(tmp_path), registry=_Registry()).execute_plan(_plan())[0]

    assert receipt.invoked is False
    assert receipt.gate_passed is False
    assert receipt.outcome["error"] == "executor_exception"
    assert "detail" not in receipt.outcome
    assert secret_marker not in json.dumps(receipt.outcome, sort_keys=True)
    assert receipt.telemetries["missing_evidence_reason"] == "executor_exception"
    assert receipt.telemetries["telemetry_source"] == "unavailable"


def test_executor_skill_receipt_replaces_matching_selected_only_placeholder(monkeypatch, tmp_path):
    slot = SkillSlot(role="SCOUT", skill_id="issue-488-scout")

    def invoked_executor(plan: CapabilityExecutionPlan, _task_desc: str) -> CapabilityReceipt:
        return CapabilityReceipt(
            capability_name=plan.required_capabilities[0],
            selected=True,
            invoked=True,
            evidence_id="ev_cap_physical",
            gate_passed=True,
            outcome={"execution_state": "SUCCESS"},
            skill_receipts=[
                SkillReceipt(
                    skill_id="issue-488-scout",
                    selected=True,
                    used=True,
                    evidence_id="ev_skill_physical",
                    outcome={"execution_state": "SUCCESS"},
                )
            ],
            telemetries={
                "wall_time_ms": 1,
                "overhead_ms": 1,
                "token_usage": 0,
                "provider_costs": 0.0,
                "model_calls": 0,
                "telemetry_source": "measured",
                "claimable": False,
            },
        )

    monkeypatch.setattr(controls_module, "get_executor", lambda _name: invoked_executor)

    receipt = ExecutorControls(str(tmp_path), registry=_Registry()).execute_plan(
        _plan(slots=[slot])
    )[0]

    matching = [r for r in receipt.skill_receipts if r.skill_id == "issue-488-scout"]
    assert len(matching) == 1
    assert matching[0].used is True
    assert matching[0].evidence_id == "ev_skill_physical"
    assert matching[0].outcome["execution_state"] == "SUCCESS"


@pytest.mark.parametrize("gate_capability", ["artifact_gate", "claim_gate"])
def test_gate_compatibility_remains_fail_closed_without_evidence(tmp_path, gate_capability):
    receipt = ExecutorControls(str(tmp_path), registry=_Registry()).execute_plan(
        _plan(gate_capability)
    )[0]

    assert receipt.invoked is True
    assert receipt.gate_passed is False
    assert receipt.outcome["compatibility_gate_evaluated"] is True


@pytest.mark.parametrize("gate_capability", ["artifact_gate", "claim_gate"])
def test_gate_compatibility_can_pass_with_structural_evidence(tmp_path, gate_capability):
    (tmp_path / "wiki_audit.json").write_text("{}", encoding="utf-8")

    receipt = ExecutorControls(str(tmp_path), registry=_Registry()).execute_plan(
        _plan(gate_capability)
    )[0]

    assert receipt.invoked is True
    assert receipt.gate_passed is True
    assert receipt.outcome["compatibility_gate_evaluated"] is True


def test_router_learning_records_failed_for_non_invocation(monkeypatch, tmp_path):
    from nexus.core import capability_constraints as constraints_module
    from nexus.core import capability_selector as selector_module
    from nexus.core import capability_signal_set as signal_module
    from nexus.core.router import SkillsRouter

    class _SignalSet:
        @classmethod
        def from_context(cls, *_args, **_kwargs):
            return object()

    class _Constraints:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    class _Selector:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def select_capabilities(self, *_args, **_kwargs):
            return _plan()

    monkeypatch.setattr(signal_module, "CapabilitySignalSet", _SignalSet)
    monkeypatch.setattr(constraints_module, "CapabilityConstraints", _Constraints)
    monkeypatch.setattr(selector_module, "CapabilitySelector", _Selector)
    monkeypatch.setattr(controls_module, "get_executor", lambda _name: _non_invoked_executor)
    monkeypatch.setenv("NEXUS_LEARNING_LOOP_WRITE_ENABLED", "0")

    router = SkillsRouter.__new__(SkillsRouter)
    router.project_root = str(tmp_path)
    router.run_dir = str(tmp_path)
    router.mem_palace = None
    router.firewall = object()
    router.p_loop = object()

    router.route_candidates("P", {"task_id": "task-488", "attempt_id": "attempt-1"})

    learning_path = tmp_path / ".nexus" / "memory" / "learning_episodes.jsonl"
    rows = [json.loads(line) for line in learning_path.read_text(encoding="utf-8").splitlines()]
    episode = rows[-1]
    assert episode["terminal_outcome"] == "FAILED"
    assert episode["terminal_evidence"]["verifier_status"] == "failed"
    assert episode["receipts"][0]["invoked"] is False
    assert episode["receipts"][0]["gate_passed"] is False
