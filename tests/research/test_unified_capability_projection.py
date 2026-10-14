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
    # research_route is a routing node: the runtime skip reason is kept, the receipt says
    # NOT_EXECUTABLE (wiring plan PR-1).
    assert (
        out["research_route"]["unified_runtime_reason"]
        == "unified_runtime:SKIPPED:SKIPPED_POLICY_NOT_TRIGGERED"
    )
    assert out["research_route"]["failure_reason"] == "NOT_EXECUTABLE:control_plane_routing_node"
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


# --- Wiring plan PR-1: reporting truth ------------------------------------------------------


def _stale_flow_receipt(name: str) -> dict:
    """A flow receipt as the bench rows carry it: not invoked, stale simulated receipt_base."""

    from nexus_runtime.planning.evidence.claim_boundary import evaluate_claim_boundary
    from nexus_runtime.planning.evidence.receipt_base import project_child_receipt_base

    stale = evaluate_claim_boundary(
        simulated=True, claim_eligible=False, receipt_present=False, model_calls=0
    ).to_dict()
    return {
        "name": name,
        "selected": True,
        "invoked": False,
        "evidence_refs": [],
        "failure_reason": "selected_without_invocation",
        "receipt_base": project_child_receipt_base(
            source_world="B",
            source_component="capability_receipt_engine",
            stage_name=name,
            stage_payload={"name": name, "selected": True, "invoked": False},
            claim_boundary=stale,
        ),
    }


def _overlay_one(name: str, stage: dict, *, capability_results: dict | None = None) -> dict:
    receipt = {"task_id": "sprint-z-s0-a1", "capabilities": [stage]}
    if capability_results is not None:
        receipt["capability_results"] = capability_results
    stages = project_unified_capability_stages([receipt])
    return overlay_unified_capability_receipts([_stale_flow_receipt(name)], stages)[0]


def test_overlay_reprojects_stale_receipt_base_when_runtime_attests_real() -> None:
    from scripts.bench.strict_llm_baseline import classify_receipt

    out = _overlay_one("acceptance_check", _stage("acceptance_check", "INVOKED"))

    assert out["invoked"] is True
    boundary = out["receipt_base"]["claim_boundary"]
    assert boundary["simulated"] is False
    assert boundary["receipt_present"] is True
    assert out["receipt_base"]["receipt_hash"]
    assert classify_receipt(out) == "real"


def test_overlay_keeps_simulated_when_runtime_says_simulated() -> None:
    from scripts.bench.strict_llm_baseline import classify_receipt

    stage = _stage("plan_quality_gate", "INVOKED")
    stage["claim_boundary"] = {"simulated": True, "claim_eligible": False}
    out = _overlay_one("plan_quality_gate", stage)

    assert out["invoked"] is True
    assert out["claim_boundary"]["simulated"] is True
    assert out["receipt_base"]["claim_boundary"]["simulated"] is True
    assert classify_receipt(out) == "simulated"


def test_jit_validation_and_simulated_outcomes_stay_simulated_regardless() -> None:
    from scripts.bench.strict_llm_baseline import classify_receipt

    # Runtime boundary says simulated=false, but jit_validation is a mock by design.
    jit = _overlay_one("jit_validation", _stage("jit_validation", "INVOKED"))
    assert jit["claim_boundary"]["simulated"] is True
    assert jit["receipt_base"]["claim_boundary"]["simulated"] is True
    assert jit["simulated_reason"] == "executor_simulated_by_design"
    assert classify_receipt(jit) == "simulated"

    # Any executor whose outcome declares simulated=True stays simulated as well.
    outcome = {"response": {"response": {"outcome": {"simulated": True}}}}
    other = _overlay_one(
        "pregate", _stage("pregate", "INVOKED"), capability_results={"pregate": outcome}
    )
    assert other["outcome_simulated"] is True
    assert other["receipt_base"]["claim_boundary"]["simulated"] is True
    assert classify_receipt(other) == "simulated"


def test_control_plane_and_routing_nodes_get_not_executable_receipts() -> None:
    from scripts.bench.strict_llm_baseline import classify_receipt

    stages = project_unified_capability_stages([
        _receipt(
            "t",
            # research_route invoked, runtime attests simulated (auth-blocked research body)
            {**_stage("research_route", "INVOKED"), "claim_boundary": {"simulated": True}},
            _stage("pregate", "INVOKED"),
        )
    ])
    receipts = [_stale_flow_receipt("direct_mode"), _stale_flow_receipt("research_route")]
    out = {row["name"]: row for row in overlay_unified_capability_receipts(receipts, stages)}

    direct = out["direct_mode"]
    assert direct["invoked"] is False
    assert direct["failure_reason"] == "NOT_EXECUTABLE:control_plane_reference"
    assert direct["execution_state"] == "NOT_EXECUTABLE"
    assert direct["unified_runtime_reason"] == "unified_runtime:NOT_SELECTED"
    assert classify_receipt(direct) == "not_executable"

    route = out["research_route"]
    assert route["invoked"] is False
    assert route["evidence_refs"] == []
    assert route["failure_reason"] == "NOT_EXECUTABLE:control_plane_routing_node"
    assert classify_receipt(route) == "not_executable"


def test_research_route_attested_real_invocation_is_not_relabelled() -> None:
    out = _overlay_one("research_route", _stage("research_route", "INVOKED"))
    assert out["invoked"] is True
    assert out["receipt_base"]["claim_boundary"]["simulated"] is False
    assert "execution_state" not in out


def test_integration_manager_is_never_selected_by_the_flow_plan() -> None:
    from nexus.app.research_receipt_runtime import runtime_receipt_plan_payload
    from nexus.core.repo_root import REPO_ROOT
    from nexus.engine.capability_planner import CapabilityPlanner
    from nexus.research.flow.capability_planning import drop_archived_capabilities

    raw = (
        CapabilityPlanner(shared_playbook_root=REPO_ROOT)
        .plan(
            task_desc="integrate the drift check and merge the module",
            task_type="bugfix",
            route={"recommended_flow": "hybrid"},
        )
        .to_dict()
    )
    plan = drop_archived_capabilities(raw)
    for key in ("selected_capabilities", "required_capabilities", "conditional_capabilities"):
        assert "integration_manager" not in plan[key]
    if "integration_manager" in raw["selected_capabilities"]:
        assert "integration_manager" in plan["forbidden_capabilities"]
        assert plan["signal_snapshot"]["archived_capabilities_dropped"] == {
            "integration_manager": "archived_retired_integration_manager_2026-10-13"
        }

    forced = {
        **raw,
        "selected_capabilities": [*raw["selected_capabilities"], "integration_manager"],
    }
    assert (
        "integration_manager"
        not in runtime_receipt_plan_payload(forced, {})["selected_capabilities"]
    )
    receipts = build_capability_receipt_payloads(forced, {"capabilities": {}})
    assert "integration_manager" not in {item["name"] for item in receipts}
