import json
from pathlib import Path

from nexus.app import research_flow_service
from nexus.research.flow.report_io import write_output_file
from nexus.research.flow.governance_packets import (
    governance_events_packet,
    research_preflight_packet,
    research_session_packet,
)
from nexus.research.flow.capability_evidence import (
    augment_local_msa_bench_evidence,
    capability_evidence,
    ultra_review_gate_evidence,
)
from nexus.research.flow.capability_planning import (
    benchmark_skill_mount_requests_from_env,
    build_route_executor_flags,
    compose_capability_plan,
    runtime_skill_overlay_requested,
)
from nexus.research.flow.runtime_decision import (
    asi_record,
    claim_check_summary,
    detect_plateau,
    hitl_payload,
    nexus_tier,
)
from nexus.research.flow.runtime_state import (
    parse_tuning_knobs,
    read_belief_confidence_fast,
    read_capability_tuning_fast,
    read_phase_slo_summary_fast,
)
from nexus.research.flow.task_classifier import is_strictly_doc_fix


def test_runtime_state_leaf_normalizes_missing_invalid_and_tuning(tmp_path: Path, monkeypatch):
    assert read_belief_confidence_fast(tmp_path) == 1.0
    belief = tmp_path / ".nexus" / "belief_state.json"
    belief.parent.mkdir(parents=True)
    belief.write_text(json.dumps({"confidence": 1.5}), encoding="utf-8")
    assert read_belief_confidence_fast(tmp_path) == 1.0

    tuning = tmp_path / "tuning.json"
    tuning.write_text(json.dumps({"knobs": {"candidate_boost": 9, "baseline_fast_sec": "0.5"}}), encoding="utf-8")
    monkeypatch.setenv("NEXUS_CAPABILITY_TUNING_FILE", str(tuning))
    assert read_capability_tuning_fast(tmp_path)["knobs"]["baseline_fast_sec"] == "0.5"
    knobs = parse_tuning_knobs(read_capability_tuning_fast(tmp_path))
    assert knobs.candidate_boost == 2
    assert knobs.baseline_fast_sec == 0.5

    assert read_phase_slo_summary_fast(tmp_path)["reason"] == "phase_slo_summary_missing"
    slo = tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    slo.parent.mkdir(parents=True, exist_ok=True)
    slo.write_text("{not-json", encoding="utf-8")
    assert read_phase_slo_summary_fast(tmp_path)["reason"] == "phase_slo_summary_invalid"


def test_runtime_decision_leaf_preserves_route_and_claim_contracts():
    assert nexus_tier({"risk_score": 99}, force_flow=None)["tier"] == "full"
    assert nexus_tier({"risk_score": 1}, force_flow=None)["tier"] == "light"
    claim = claim_check_summary(
        task_desc="verify claim",
        tests_passed=True,
        artifact_summary={"changed": False, "verification_only": True, "pytest_cmd": "pytest"},
        route={"recommended_reason": "fixture"},
    )
    assert claim["passed"] is True
    assert [item["claim_id"] for item in claim["results"]] == [
        "tests_passed",
        "artifact_or_verification",
        "claim_keyword_requires_evidence",
    ]
    assert hitl_payload(route_confidence=0.2, route={"route_features": {"router_hint_mode": "strict"}}, task_id="Task A")[
        "attach_session"
    ] == "hitl-task-a"
    assert asi_record(
        run_id=1,
        task_desc="task",
        recommended_flow="hyper_sprint",
        chosen_flow="baseline",
        status="FAILED",
        error="boom",
        route_confidence=0.12345,
    )["status"] == "discard"
    assert detect_plateau(
        [
            {"status": "discard", "family": "x", "metric": 0.1},
            {"status": "discard", "family": "x", "metric": 0.11},
            {"status": "discard", "family": "x", "metric": 0.12},
            {"status": "discard", "family": "x", "metric": 0.1},
        ]
    )["detected"] is True


def test_report_io_and_task_classifier_keep_facade_aliases(tmp_path: Path):
    out = write_output_file(tmp_path, Path("reports/out.json"), {"ok": True})
    assert out == (tmp_path / "reports" / "out.json").resolve()
    assert json.loads(out.read_text(encoding="utf-8")) == {"ok": True}
    assert research_flow_service._write_output_file is write_output_file

    assert is_strictly_doc_fix("documentation typo", "README.md")[0] is True
    assert is_strictly_doc_fix("fix bug", "README.md")[0] is False
    assert research_flow_service._is_strictly_doc_fix is is_strictly_doc_fix


def test_research_flow_service_keeps_leaf_aliases():
    assert research_flow_service._parse_tuning_knobs is parse_tuning_knobs
    assert research_flow_service.read_belief_confidence_fast is read_belief_confidence_fast
    assert research_flow_service.read_capability_tuning_fast is read_capability_tuning_fast
    assert research_flow_service.read_phase_slo_summary_fast is read_phase_slo_summary_fast
    assert research_flow_service._nexus_tier is nexus_tier
    assert research_flow_service._claim_check_summary is claim_check_summary
    assert research_flow_service._hitl_payload is hitl_payload
    assert research_flow_service._asi_record is asi_record
    assert research_flow_service._detect_plateau is detect_plateau


def test_governance_packets_keep_schema_and_facade_aliases(tmp_path: Path):
    route = {
        "recommended_flow": "hyper_sprint",
        "recommended_reason": "hard_task",
        "research_context": {"risk_flags": ["claim_uncertainty"], "blocked_assumptions": ["missing evidence"]},
    }
    preflight = research_preflight_packet(route=route, route_confidence=0.12345, task_id=None)
    assert preflight["decision"] == "requires_evidence"
    assert preflight["route_confidence"] == 0.1235

    session = research_session_packet(
        task_id=None,
        status="SUCCESS",
        asi_record={"hypothesis": "Fix Race", "status": "keep", "family": "flow:hyper"},
        route=route,
        research_preflight=preflight,
    )
    assert session["task_id"] == "fix-race"
    assert session["status"] == "keep"

    packet = governance_events_packet(
        repo_root=tmp_path,
        task_id="task-1",
        receipt_slug="receipt-1",
        artifact_verified=False,
        claim_probe={"eligible": True, "gate_passed": False},
    )
    assert packet["summary"]["event_types"] == ["audit_failed", "learning_decision"]

    assert research_flow_service._research_preflight_packet is research_preflight_packet
    assert research_flow_service._research_session_packet is research_session_packet
    assert research_flow_service._governance_events_packet is governance_events_packet


def test_capability_evidence_leaf_preserves_receipt_contracts(tmp_path: Path):
    evidence = capability_evidence(
        result_report={
            "candidate_summaries": [{"source": "swarm", "hint": "create:x sync:y test:z"}],
            "nightshift_report_path": "night.md",
        },
        learning_trace={"drone_crystals": ["drone.json"]},
        nightshift_recommended=True,
    )
    assert evidence["swarm_evidence_count"] == 1
    assert evidence["drone_invoked_count"] == 1
    assert evidence["nightshift_failure_reason"] == "report_without_recovery"

    augmented = augment_local_msa_bench_evidence(
        tmp_path,
        task_id="task-1",
        task_desc="route-oracle-research route-oracle-lancedb semantic_searcher refs swarm drone nightshift",
        task_type="research-backed",
        evidence=evidence,
        artifact_verified=True,
        route_executor_flags={"enable_swarm": True},
    )
    assert augmented["research_gate_passed"] is True
    assert augmented["lancedb_gate_passed"] is True
    assert augmented["semantic_searcher_gate_passed"] is True
    assert augmented["swarm_used"] is True
    assert augmented["drone_used"] is True
    assert augmented["nightshift_recovered"] is True

    disabled = ultra_review_gate_evidence(
        repo_root=tmp_path,
        task_desc="review",
        route_decision={"executor_controls": {"enable_ultra_review": True}},
    )
    assert disabled["reason"] == "feature_flag_disabled"

    assert research_flow_service._capability_evidence is capability_evidence
    assert research_flow_service._augment_local_msa_bench_evidence is augment_local_msa_bench_evidence
    assert research_flow_service._ultra_review_gate_evidence is ultra_review_gate_evidence


def test_capability_planning_leaf_keeps_compatibility_contract(monkeypatch):
    stack = compose_capability_plan(
        task_desc="fix race",
        task_type="bug",
        recommended_flow="hyper_sprint",
        route_features={"candidate_factory_readiness_estimate": {"ready": True, "estimated_candidates": 3}},
        research_context={"recommended_capabilities": ["autoreason", "ultra_review"]},
        target_file="target.py",
    )
    assert stack["schema_version"] == "legacy_capability_stack_v2_compat"
    assert "hyper_sprint" in stack["selected_capabilities"]
    assert stack["target_file"] == "target.py"

    route = {"capability_plan": {"selected_capabilities": ["swarm", "drone"]}}
    flags = build_route_executor_flags(task_desc="task", task_type="bug", route=route)
    assert flags["enable_swarm"] is True
    assert flags["enable_drone"] is True

    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNT_REQUESTS", '["tdd"]')
    assert benchmark_skill_mount_requests_from_env(task_id="task-1") == [
        {"skill_id": "tdd", "source": "benchmark_env_request"}
    ]
    assert runtime_skill_overlay_requested({"runtime_skill_policy_overlay_path": "policy.json"}) is True

    assert research_flow_service.compose_capability_plan is compose_capability_plan
    assert research_flow_service.build_route_executor_flags is build_route_executor_flags
    assert research_flow_service._benchmark_skill_mount_requests_from_env is benchmark_skill_mount_requests_from_env
    assert research_flow_service._runtime_skill_overlay_requested is runtime_skill_overlay_requested
