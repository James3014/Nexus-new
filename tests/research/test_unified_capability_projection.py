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
            "receipt_present": invoked,
        },
    }


def _bundle(*stages: dict) -> dict:
    """Evidence bundle holding a record for every ref an invoked stage carries."""

    return {
        "entries": [
            {
                "name": stage["name"],
                "physical_callable": f"capability_executor_registry:{stage['name']}",
                "evidence_ids": list(stage.get("evidence_refs") or []),
            }
            for stage in stages
            if stage.get("status") == "INVOKED"
        ]
    }


def _receipt(task_id: str, *stages: dict) -> dict:
    return {
        "task_id": task_id,
        "capabilities": list(stages),
        "capability_evidence_bundle": _bundle(*stages),
    }


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
    receipt = _receipt("sprint-z-s0-a1", stage)
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


def test_stage_simulated_flag_disagreeing_with_boundary_stays_simulated() -> None:
    """Codex probe: INVOKED, stage.simulated=True, claim_boundary.simulated=False, refs present."""

    from scripts.bench.strict_llm_baseline import classify_receipt

    forged = {**_stage("acceptance_check", "INVOKED"), "simulated": True}
    forged["claim_boundary"] = {"simulated": False, "claim_eligible": True}
    out = _overlay_one("acceptance_check", forged)
    assert out["invoked"] is True
    assert out["claim_boundary"]["simulated"] is True
    assert out["receipt_base"]["claim_boundary"]["simulated"] is True
    assert classify_receipt(out) == "simulated"

    # A boundary that says no receipt is present is not real either.
    absent = _stage("pregate", "INVOKED")
    absent["claim_boundary"] = {"simulated": False, "receipt_present": False}
    assert classify_receipt(_overlay_one("pregate", absent)) == "simulated"

    # And a stage without the simulated flag at all is not attested.
    from nexus.research.flow.unified_capability_projection import runtime_attests_real

    bare = {
        "claim_boundary": {"simulated": False, "receipt_present": True},
        "evidence_refs": ["ev"],
        "refs_resolved": True,
    }
    assert runtime_attests_real({"name": "pregate"}, bare) is False
    assert runtime_attests_real({"name": "pregate"}, {**bare, "simulated": False}) is True
    assert (
        runtime_attests_real({"name": "pregate"}, {**bare, "simulated": False, "evidence_refs": []})
        is False
    )


def test_archived_capabilities_are_dropped_from_the_route_decision_and_empty_plans() -> None:
    from nexus.app.research_receipt_runtime import runtime_receipt_plan_payload
    from nexus.core.repo_root import REPO_ROOT
    from nexus.engine.capability_planner import CapabilityPlanner
    from nexus.engine.route_decision_adapter import build_route_decision
    from nexus.research.flow.capability_planning import drop_archived_capabilities

    plan = CapabilityPlanner(shared_playbook_root=REPO_ROOT).plan(
        task_desc="integrate the drift check and merge the module",
        task_type="bugfix",
        route={"recommended_flow": "hybrid"},
    )
    decision = build_route_decision(
        task_id="t", task_desc="integrate", task_type="bugfix", recommended_flow="hybrid", plan=plan
    ).to_dict()
    cleaned = drop_archived_capabilities(decision)
    for key in ("selected_capabilities", "required_capabilities", "conditional_capabilities"):
        assert "integration_manager" not in cleaned[key]
    stop = cleaned.get("stop_policy") or {}
    assert "integration_manager" not in (stop.get("tactical_sequence") or [])
    steps = stop.get("tactical_tool_map") or []
    assert all(step.get("capability") != "integration_manager" for step in steps)
    assert all(step.get("after") != "integration_manager" for step in steps)

    def _nested(value: object) -> list[object]:
        found: list[object] = []
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "archived_capabilities_dropped":
                    continue
                if key == "integration_manager":
                    found.append(key)
                if key == "selected_capabilities" and "integration_manager" in (item or []):
                    found.append(item)
                found.extend(_nested(item))
        elif isinstance(value, list):
            for item in value:
                found.extend(_nested(item))
        return found

    assert _nested(cleaned["signal_snapshot"]) == []
    if "integration_manager" in decision["selected_capabilities"]:
        assert "integration_manager" in cleaned["forbidden_capabilities"]
        assert _nested(decision["signal_snapshot"]) != []  # the raw decision did carry it

    # No selected capability at all: the archive filter still applies to the other lists.
    empty = {"selected_capabilities": [], "conditional_capabilities": ["integration_manager"]}
    out = runtime_receipt_plan_payload(empty, {})
    assert out["conditional_capabilities"] == []
    assert "integration_manager" in out["forbidden_capabilities"]


def test_unresolved_refs_or_missing_receipt_present_stay_simulated() -> None:
    """Codex round-2 probe: a made-up ref, or no receipt_present, is never real."""

    from scripts.bench.strict_llm_baseline import classify_receipt

    stage = {**_stage("pregate", "INVOKED"), "evidence_refs": ["made-up-ref"]}
    stage["claim_boundary"] = {"simulated": False, "claim_eligible": False}  # no receipt_present
    forged = {"task_id": "t", "capabilities": [stage]}  # no evidence record anywhere
    stages = project_unified_capability_stages([forged])
    out = overlay_unified_capability_receipts([_stale_flow_receipt("pregate")], stages)[0]
    assert stages[0]["refs_resolved"] is False
    assert classify_receipt(out) == "simulated"

    # receipt_present=True but the ref resolves nowhere -> still simulated.
    stage["claim_boundary"] = {"simulated": False, "receipt_present": True}
    stages = project_unified_capability_stages([forged])
    out = overlay_unified_capability_receipts([_stale_flow_receipt("pregate")], stages)[0]
    assert classify_receipt(out) == "simulated"

    # The same ref held by the bundle -> real.
    held = {**forged, "capability_evidence_bundle": _bundle(stage)}
    stages = project_unified_capability_stages([held])
    out = overlay_unified_capability_receipts([_stale_flow_receipt("pregate")], stages)[0]
    assert stages[0]["refs_resolved"] is True
    assert classify_receipt(out) == "real"

    # A bundle entry without a physical callable is not an evidence record.
    hollow = {
        **forged,
        "capability_evidence_bundle": {"entries": [{"evidence_ids": ["made-up-ref"]}]},
    }
    assert project_unified_capability_stages([hollow])[0]["refs_resolved"] is False

    # Resolved through the capability's own stage record (postflight stages are not in the bundle).
    record = {
        "capability_results": {
            "pregate": {
                "physical_callable": "capability_executor_registry:pregate",
                "evidence_refs": ["made-up-ref"],
                "response": {"status": "FAILED"},
            }
        }
    }
    stages = project_unified_capability_stages([{**forged, **record}])
    assert stages[0]["refs_resolved"] is True

    # receipt_present missing with a resolved ref -> simulated.
    stage["claim_boundary"] = {"simulated": False}
    stages = project_unified_capability_stages([held])
    out = overlay_unified_capability_receipts([_stale_flow_receipt("pregate")], stages)[0]
    assert classify_receipt(out) == "simulated"


def test_archived_walker_leaves_no_archived_name_outside_the_audit_places() -> None:
    import json

    from nexus.research.flow.capability_planning import drop_archived_capabilities

    plan = {
        "selected_capabilities": ["pregate", "integration_manager"],
        "forbidden_capabilities": [],
        "decision_trace": [{"capability": "integration_manager", "state": "conditional"}],
        "signal_snapshot": {"reasons": {"integration_manager": ["x"], "pregate": ["y"]}},
        "stop_policy": {
            "tactical_sequence": ["pregate", "integration_manager", "claim_gate"],
            "tactical_tool_map": [
                {"capability": "integration_manager", "after": "pregate"},
                {
                    "capability": "claim_gate",
                    "after": "integration_manager",
                    "plan": {"selected_capabilities": ["integration_manager", "pregate"]},
                },
                {"capability": "delivery_gate", "after": "swarm_quiet_moment"},
            ],
        },
        "replan_trace": [{"active_capabilities": ["integration_manager"], "note": {"x": 1}}],
    }
    cleaned = drop_archived_capabilities(plan)
    rest = {
        k: v for k, v in cleaned.items() if k not in {"forbidden_capabilities", "decision_trace"}
    }
    rest["signal_snapshot"] = {
        k: v for k, v in rest["signal_snapshot"].items() if k != "archived_capabilities_dropped"
    }
    text = json.dumps(rest)
    assert "integration_manager" not in text
    assert "swarm_quiet_moment" not in text
    steps = cleaned["stop_policy"]["tactical_tool_map"]
    assert steps[0] == {
        "capability": "claim_gate",
        "after": "pregate",
        "plan": {"selected_capabilities": ["pregate"]},
    }
    assert steps[1]["after"] is None
    assert "integration_manager" in cleaned["forbidden_capabilities"]
    assert cleaned["decision_trace"][0]["state"] == "forbidden"
    assert "integration_manager" in cleaned["signal_snapshot"]["archived_capabilities_dropped"]


def test_simulation_markers_anywhere_in_the_outcome_stay_simulated() -> None:
    """Reviewer probes: markers under any key (bounded depth) keep the receipt simulated."""

    from scripts.bench.strict_llm_baseline import classify_receipt

    for outcome in (
        {"response": {"result": {"simulated": True}}},
        {"response": {"data": {"claim": "SIMULATED"}}},
        {"response": {"items": [{"kind": " stub "}]}},
        {"response": {"provider": "Mock"}},
    ):
        out = _overlay_one(
            "pregate",
            _stage("pregate", "INVOKED"),
            capability_results={
                "pregate": {
                    **outcome,
                    "physical_callable": "capability_executor_registry:pregate",
                    "evidence_refs": ["ev_cap_pregate"],
                }
            },
        )
        assert out["outcome_simulated"] is True, outcome
        assert classify_receipt(out) == "simulated", outcome


def test_control_plane_reference_never_upgrades_even_with_all_real_signals() -> None:
    from scripts.bench.strict_llm_baseline import classify_receipt

    out = _overlay_one("direct_mode", _stage("direct_mode", "INVOKED"))
    assert out["invoked"] is False
    assert out["failure_reason"] == "NOT_EXECUTABLE:control_plane_reference"
    assert classify_receipt(out) == "not_executable"
    # research_route (routing node) with the same all-real signals may be upgraded.
    assert classify_receipt(
        _overlay_one("research_route", _stage("research_route", "INVOKED"))
    ) == ("real")
    # ... but not when its refs do not resolve.
    forged = {**_stage("research_route", "INVOKED"), "evidence_refs": ["made-up"]}
    stages = project_unified_capability_stages([{"task_id": "t", "capabilities": [forged]}])
    route = overlay_unified_capability_receipts([_stale_flow_receipt("research_route")], stages)[0]
    assert classify_receipt(route) == "not_executable"


def test_archived_names_match_after_normalising_and_in_nested_lists() -> None:
    import json

    from nexus.research.flow.capability_planning import drop_archived_capabilities

    plan = {
        "selected_capabilities": [" integration_manager", "Integration_Manager", "pregate"],
        "conditional_capabilities": [["integration_manager"], ["pregate"]],
        "forbidden_capabilities": [],
        "signal_snapshot": {" Integration_Manager ": {"x": 1}},
    }
    cleaned = drop_archived_capabilities(plan)
    assert cleaned["selected_capabilities"] == ["pregate"]
    assert cleaned["conditional_capabilities"] == [[], ["pregate"]]
    assert cleaned["forbidden_capabilities"] == ["integration_manager"]
    rest = {k: v for k, v in cleaned.items() if k != "forbidden_capabilities"}
    rest["signal_snapshot"] = {
        k: v for k, v in rest["signal_snapshot"].items() if k != "archived_capabilities_dropped"
    }
    assert "integration_manager" not in json.dumps(rest).lower()
