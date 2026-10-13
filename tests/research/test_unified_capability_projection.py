"""Online A/B gap A: flow receipts must reflect what the executing UnifiedRuntime ran."""

from __future__ import annotations

from nexus.app.research_receipt_runtime import build_capability_receipt_payloads
from nexus.research.flow.auto_flow_executor import build_hyper_sprint_report
from nexus.research.flow.baseline_report import baseline_report_from_meta
from nexus.research.flow.unified_capability_projection import (
    UNIFIED_RUNTIME_SELECTION_SOURCE,
    overlay_unified_capability_receipts,
    project_unified_capability_stages,
)


def _stage(
    name: str, status: str, *, reason: str = "", refs: list[str] | None = None, gate: bool = False
) -> dict:
    invoked = status == "INVOKED"
    return {
        "name": name,
        "status": status,
        "invoked": invoked,
        "skip_reason": reason,
        "gate_passed": gate,
        "evidence_refs": refs if refs is not None else ([f"ev_cap_{name}"] if invoked else []),
        "simulated": not invoked,
        "claim_boundary": {
            "simulated": not invoked,
            "claim_eligible": False,
            "evidence_complete": invoked,
        },
    }


def _receipt(task_id: str, *stages: dict) -> dict:
    return {"task_id": task_id, "capabilities": list(stages)}


def test_projection_merges_attempts_and_prefers_invoked() -> None:
    first = _receipt(
        "sprint-x-s0-a1", _stage("research_route", "SKIPPED", reason="SKIPPED_POLICY_NOT_TRIGGERED")
    )
    second = _receipt(
        "sprint-x-s0-a2",
        _stage("research_route", "INVOKED"),
        _stage("pregate", "INVOKED", gate=True),
    )
    third = _receipt(
        "sprint-x-s0-a3", _stage("research_route", "SKIPPED", reason="SKIPPED_POLICY_NOT_TRIGGERED")
    )

    stages = {
        row["name"]: row
        for row in project_unified_capability_stages([first, second, third, "junk", None])
    }

    assert stages["research_route"]["status"] == "INVOKED"
    assert stages["research_route"]["runtime_task_id"] == "sprint-x-s0-a2"
    assert stages["research_route"]["attempts"] == 3
    assert stages["pregate"]["gate_passed"] is True
    assert stages["pregate"]["claim_boundary"]["simulated"] is False


def test_overlay_marks_runtime_invoked_capability_as_invoked_with_runtime_evidence() -> None:
    stages = project_unified_capability_stages([
        _receipt("t", _stage("pregate", "INVOKED", gate=False))
    ])
    receipts = [
        {
            "name": "pregate",
            "selected": True,
            "invoked": False,
            "evidence_refs": [],
            "failure_reason": "selected_without_invocation",
        }
    ]

    out = overlay_unified_capability_receipts(receipts, stages)

    assert out[0]["invoked"] is True
    assert out[0]["evidence_refs"] == ["ev_cap_pregate"]
    assert out[0]["selection_source"] == UNIFIED_RUNTIME_SELECTION_SOURCE
    assert out[0]["failure_reason"] == "evidence_without_gate_pass"
    assert out[0]["outcome_contributed"] is False
    assert out[0]["claim_boundary"]["simulated"] is False


def test_overlay_names_runtime_skip_reason_and_never_invents_invocation() -> None:
    stages = project_unified_capability_stages([
        _receipt(
            "t",
            _stage("research_route", "SKIPPED", reason="SKIPPED_POLICY_NOT_TRIGGERED"),
            _stage(
                "repair_loop",
                "SELECTED_NOT_EXECUTED",
                reason="planner_selected_no_runtime_executor",
            ),
            # invoked status without evidence refs is not enough
            _stage("jit_validation", "INVOKED", refs=[]),
        )
    ])
    receipts = [
        {
            "name": "research_route",
            "selected": True,
            "invoked": False,
            "failure_reason": "selected_without_invocation",
        },
        {
            "name": "repair_loop",
            "selected": True,
            "invoked": False,
            "failure_reason": "selected_without_invocation",
        },
        {
            "name": "jit_validation",
            "selected": True,
            "invoked": False,
            "failure_reason": "selected_without_invocation",
        },
        {
            "name": "hyper",
            "selected": True,
            "invoked": False,
            "failure_reason": "selected_without_invocation",
        },
        {
            "name": "artifact_gate",
            "selected": True,
            "invoked": True,
            "evidence_refs": ["artifact:x"],
        },
    ]

    out = {row["name"]: row for row in overlay_unified_capability_receipts(receipts, stages)}

    assert out["research_route"]["invoked"] is False
    assert (
        out["research_route"]["failure_reason"]
        == "unified_runtime:SKIPPED:SKIPPED_POLICY_NOT_TRIGGERED"
    )
    assert out["repair_loop"]["failure_reason"] == (
        "unified_runtime:SELECTED_NOT_EXECUTED:planner_selected_no_runtime_executor"
    )
    assert out["jit_validation"]["invoked"] is False
    # No runtime stage -> the executing planner did not select it; invoked ones untouched.
    assert out["hyper"]["invoked"] is False
    assert out["hyper"]["failure_reason"] == "unified_runtime:NOT_SELECTED"
    assert out["artifact_gate"] == receipts[4]


def test_build_capability_receipt_payloads_consumes_unified_runtime_stages() -> None:
    stages = project_unified_capability_stages([
        _receipt(
            "t", _stage("pregate", "INVOKED"), _stage("plan_quality_gate", "INVOKED", gate=True)
        )
    ])
    receipts = build_capability_receipt_payloads(
        {"selected_capabilities": ["pregate", "plan_quality_gate"]},
        {"capabilities": {}, "unified_runtime_capabilities": stages},
    )
    by_name = {item["name"]: item for item in receipts}

    assert by_name["pregate"]["invoked"] is True
    assert by_name["plan_quality_gate"]["gate_passed"] is True
    assert by_name["plan_quality_gate"]["selection_source"] == UNIFIED_RUNTIME_SELECTION_SOURCE


def test_flow_reports_carry_unified_runtime_stages() -> None:
    receipt = _receipt("sprint-y-s0-a1", _stage("pregate", "INVOKED"))
    baseline = baseline_report_from_meta(
        "nexus_llm_baseline", {"model_calls": 1, "unified_runtime_receipt": receipt}
    )
    assert [row["name"] for row in baseline["unified_runtime_capability_stages"]] == ["pregate"]
    assert "unified_runtime_capability_stages" not in baseline_report_from_meta(
        "local", {"model_calls": 0}
    )

    class _Result:
        status = "FAILED"
        reason = "pytest_failed"
        winner_source = "llm"
        error_codes: list[str] = []
        rejection_summary: dict[str, int] = {}
        attempt_count = 1
        model_calls = 1
        total_tokens = 10
        token_capture_status = "measured"
        unified_runtime_receipts = [receipt]

    hyper = build_hyper_sprint_report(
        _Result(), effective_stage1_timeout_sec=20, r_phase_breakdown_sec={}, candidate_summaries=[]
    )
    assert hyper["unified_runtime_capability_stages"][0]["status"] == "INVOKED"
