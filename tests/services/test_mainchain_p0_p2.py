"""P0–P2: no-new-route freeze, Planner catalog authority, shared evidence bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.engine.capability_contracts import CapabilityPlan
from nexus.engine.capability_planner import default_capability_nodes
from nexus.services.capability_evidence_bundle import (
    assert_same_baseline,
    build_capability_evidence_bundle,
    compute_bundle_hash,
    record_consumption,
    verify_capability_evidence_bundle,
)
from nexus.services.capability_registry import list_planner_capability_names
from nexus.services.mainchain_entry import run_mainchain
from nexus.services.mainchain_route_freeze import (
    FROZEN_EXECUTION_TOPOLOGIES,
    FROZEN_ROUTE_MODE_VALUES,
    MAINCHAIN_AUTHORITY,
    assert_no_forbidden_route_literals,
    assert_selection_authority_is_planner,
    build_capability_catalog,
    freeze_summary,
    scan_source_ast,
    single_planner_decision_id,
)
from nexus.services.unified_runtime import (
    UnifiedRuntime,
    UnifiedRuntimeRequest,
    normalize_online_invoker_payload,
)


class _Planner:
    def plan(self, **_: object) -> CapabilityPlan:
        return CapabilityPlan(
            schema_version="nexus_capability_plan_v1",
            selected_capabilities=[
                "codeintel",
                "memory",
                "belief",
                "swarm",
                "artifact_gate",
                "claim_gate",
                "delivery_gate",
            ],
            required_capabilities=["codeintel"],
            optional_capabilities=[],
            conditional_capabilities=[],
            pending_capabilities=[],
            forbidden_capabilities=[],
            constraints=[],
            decision_trace=[],
            replan_trace=[],
            score=1.0,
            signal_snapshot={"route_truth_source": "CapabilityPlanner"},
        )


def _online(context: dict[str, Any]) -> dict[str, Any]:
    # Capture shared baseline hash from Online context for P2 equality check.
    _online.last_baseline = str(context.get("baseline_hash") or "")
    _online.last_bundle = context.get("capability_evidence_bundle")
    return normalize_online_invoker_payload(
        provider="fixture",
        task_id=str(context.get("task_id") or ""),
        invoked=True,
        output_delivered=True,
        gate_passed=True,
        provider_call_count=1,
        response={"ok": True, "baseline_hash": context.get("baseline_hash")},
        raw_response="ok",
        evidence_refs=[f"online:{context.get('task_id')}"],
    )


_online.last_baseline = ""
_online.last_bundle = None


def test_p0_no_forbidden_route_literals_in_mainchain_modules() -> None:
    from nexus.services.mainchain_route_freeze import scan_mainchain_paths_for_forbidden_routes

    root = Path(__file__).resolve().parents[2]
    # Must cover mainchain + related call sites (gateway, local_assist, pipeline_repair).
    scan = scan_mainchain_paths_for_forbidden_routes(root)
    assert scan["ok"] is True, f"forbidden route literals: {scan['file_hits']}"
    assert scan["routing_surface_changed"] is False
    assert scan["file_hits"] == []
    assert "nexus/services/gateway.py" in scan["scanned_paths"]
    assert "nexus/services/local_assist_service.py" in scan["scanned_paths"]
    assert "nexus/engine/pipeline_repair.py" in scan["scanned_paths"]
    # Per-file AST scan must report zero hits (concatenated sources are not valid Python).
    for rel in scan["scanned_paths"]:
        text = (root / rel).read_text(encoding="utf-8")
        result = scan_source_ast(text, path=rel)
        assert result["ok"] is True, f"{rel}: {result['hits']}"
        assert result["hits"] == []
    # routing_surface_changed must be scan-derived, never a hard-coded constant.
    summary = freeze_summary(repo_root=root)
    assert summary["routing_surface_changed"] is False
    assert summary["routing_surface_scan"]["ok"] is True
    assert summary["route_authority"] == MAINCHAIN_AUTHORITY
    assert set(summary["frozen_route_modes"]) == set(FROZEN_ROUTE_MODE_VALUES)
    assert set(summary["frozen_topologies"]) == set(FROZEN_EXECUTION_TOPOLOGIES)


def test_p0_red_blocks_new_route_mode_class_and_member() -> None:
    """RED: class RouteMode(Enum): NEW = \"online_local_v2\" must BLOCK."""
    src = (
        "from enum import Enum\n"
        "class RouteMode(Enum):\n"
        '    NEW = "online_local_v2"\n'
    )
    result = scan_source_ast(src, path="tests/fixtures/fake_new_route.py")
    assert result["ok"] is False
    assert result["routing_surface_changed"] is True
    kinds = {h["kind"] for h in result["hits"]}
    assert "new_route_mode_class" in kinds or "new_route_mode_member" in kinds
    assert "new_route_mode_value" in kinds or any(
        h.get("value") == "online_local_v2" for h in result["hits"]
    )


def test_p0_red_blocks_unknown_route_mode_assign() -> None:
    """RED: route_mode=\"online_local_v2\" must BLOCK."""
    result = assert_no_forbidden_route_literals('route_mode = "online_local_v2"\n')
    assert result["ok"] is False
    assert result["routing_surface_changed"] is True
    assert any(h.get("value") == "online_local_v2" for h in result["hits"])


def test_p0_red_blocks_unknown_execution_topology_assign() -> None:
    """RED: execution_topology=\"online_local_v2\" must BLOCK."""
    result = assert_no_forbidden_route_literals(
        'execution_topology = "online_local_v2"\n'
    )
    assert result["ok"] is False
    assert result["routing_surface_changed"] is True
    assert any(
        h["kind"] == "unknown_execution_topology" for h in result["hits"]
    )


def test_p0_red_blocks_unknown_topology_in_dict() -> None:
    """RED: {\"execution_topology\": \"online_local_v2\"} must BLOCK."""
    result = assert_no_forbidden_route_literals(
        'cfg = {"execution_topology": "online_local_v2"}\n'
    )
    assert result["ok"] is False
    assert any(h.get("value") == "online_local_v2" for h in result["hits"])


def test_p0_red_blocks_unknown_route_mode_call_kwarg() -> None:
    """RED: build(route_mode=\"online_local_v2\") must BLOCK."""
    result = assert_no_forbidden_route_literals(
        'build(route_mode="online_local_v2")\n'
    )
    assert result["ok"] is False
    assert any(
        h["kind"] == "unknown_route_mode" and h.get("value") == "online_local_v2"
        for h in result["hits"]
    )


def test_p0_frozen_values_still_allowed() -> None:
    """Historical frozen route/topology contracts remain readable."""
    src = (
        'route_mode = "local_only_executed"\n'
        'execution_topology = "single_local_model"\n'
        'cfg = {"route_mode": "cloud_assisted_by_local_trace_only", '
        '"execution_topology": "local_cascade"}\n'
        'build(route_mode="local_only_planned", execution_topology="local_only")\n'
    )
    result = assert_no_forbidden_route_literals(src)
    assert result["ok"] is True, result["hits"]
    assert result["routing_surface_changed"] is False
    assert result["hits"] == []


def test_p0_single_planner_decision_id_on_mainchain_receipt() -> None:
    req = UnifiedRuntimeRequest(
        task_id="p0-freeze-001",
        workspace_revision="rev-p0",
        task_statement="scan impact risk codeintel",
        task_type="codeintel",
        route={
            "recommended_flow": "direct",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
        },
        online_enabled=True,
        online_prompt="task",
        codeintel={"scan_report_present": True, "risk_score": 3},
    )
    receipt = run_mainchain(
        req,
        online_invoker=_online,
        planner=_Planner(),
        verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"v:{c['task_id']}"],
        },
        learning=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"l:{c['task_id']}"],
        },
    )
    check = single_planner_decision_id(receipt)
    assert check["ok"] is True
    assert check["planner_decision_id"]
    assert check["selection_authority"] == "CapabilityPlanner"
    auth = assert_selection_authority_is_planner(receipt)
    assert auth["ok"] is True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False
    assert receipt.get("selection_authority") == "CapabilityPlanner"


def test_p1_catalog_covers_planner_nodes_only_planner_authority() -> None:
    from nexus.services.mainchain_route_freeze import (
        list_spxdrac_capability_names,
        validate_alias_map,
    )

    root = Path(__file__).resolve().parents[2]
    catalog = build_capability_catalog(repo_root=root)
    nodes = default_capability_nodes()
    planner = set(list_planner_capability_names())
    spx = set(list_spxdrac_capability_names())
    union = planner | spx

    # Dynamic counts — never hard-coded 51/198
    assert catalog["planner_node_count"] == len(nodes) == len(planner)
    assert catalog["spxdrac_reference_count"] == len(spx)
    assert catalog["spxdrac_reference_count"] != 0
    assert catalog["canonical_union_count"] == len(union)
    assert catalog["union_unaccounted_count"] == 0
    assert catalog["union_unaccounted"] == []
    assert catalog["union_accounted_count"] == len(union)

    assert catalog["route_authority"] == MAINCHAIN_AUTHORITY
    assert catalog["selection_authority"] == MAINCHAIN_AUTHORITY
    assert catalog["routing_surface_changed"] is False
    assert catalog["new_route_mode_introduced"] is False
    assert catalog["dual_contract_note"]["CapabilitySelector"] == (
        "spxdrac_metadata_only_not_mainchain_route"
    )

    # Alias integrity
    alias_v = validate_alias_map()
    assert alias_v["ok"] is True
    assert catalog["alias_validation"]["ok"] is True
    alias_ids = {a["id"] for a in catalog["alias_rows"]}
    canon_ids = {row["canonical_id"] for row in catalog["rows"]}
    assert alias_ids.isdisjoint(canon_ids)
    for a in catalog["alias_rows"]:
        assert a["terminal_class"] == "ALIAS_OF"
        assert a["canonical_id"] in canon_ids
        assert a["selection_authority"] == MAINCHAIN_AUTHORITY
    # Known semantic aliases
    assert "hyper_sprint" in alias_ids
    assert "swarm_multi_agent" in alias_ids
    assert "mempalace" in alias_ids
    hyper = next(r for r in catalog["rows"] if r["canonical_id"] == "hyper")
    assert "hyper_sprint" in hyper["aliases"]

    required = (
        "canonical_id",
        "aliases",
        "owner",
        "trigger",
        "executor",
        "consumer",
        "maturity",
        "runtime_eligible",
        "selection_authority",
    )
    for row in catalog["rows"]:
        assert row["route_authority"] == MAINCHAIN_AUTHORITY
        assert row["selection_authority"] == MAINCHAIN_AUTHORITY
        assert row["selector_may_decide_route"] is False
        for key in required:
            assert key in row, f"missing {key} on {row.get('canonical_id')}"

    # Historical 198: 100% terminal classification
    assert catalog["legacy_inventory_reference_count"] > 0
    assert catalog["legacy_inventory_classified_count"] == catalog[
        "legacy_inventory_reference_count"
    ]
    assert catalog["legacy_inventory_unclassified_count"] == 0
    for h in catalog["historical_classifications"]:
        assert h["terminal_class"] in {
            "CANONICAL_RUNTIME",
            "ALIAS_OF",
            "OFFLINE_ONLY",
            "EXPERIMENTAL_NOT_PROMOTED",
            "DEPRECATED",
            "NON_CAPABILITY_ARTIFACT",
        }


def test_p2_shared_evidence_before_local_and_online_same_baseline() -> None:
    class _Local:
        def __init__(self) -> None:
            self.seen_baseline = ""

        def handle(self, request: Any) -> dict[str, Any]:
            snap = {}
            if isinstance(request, dict):
                snap = dict(request.get("planner_snapshot") or {})
                task_id = request["task_id"]
            else:
                snap = dict(getattr(request, "planner_snapshot", {}) or {})
                task_id = request.task_id
            bundle = snap.get("capability_evidence_bundle") or {}
            self.seen_baseline = str(bundle.get("baseline_hash") or "")
            return {
                "task_id": task_id,
                "action": "candidate",
                "local_model_invoked": True,
                "output_delivered": True,
                "executor_invoked": True,
                "physical_callable": "LocalModelExecutor.run",
                "receipt_path": f"/tmp/{task_id}.json",
                "evidence_refs": [f"local:{task_id}"],
                "candidate_summary": {
                    "isolation_status": "isolated",
                    "selected_candidate_hash": "h1",
                    "selected_candidate_hash_matches_applied": True,
                },
                "verifier_summary": {"verifier_status": "not_run"},
                "local_outputs": {"concise_summary": "action=candidate;status=ok"},
                "outcome_contributed": True,
            }

    local = _Local()

    class _LocalPlanner:
        def plan(self, **_: object) -> CapabilityPlan:
            return CapabilityPlan(
                schema_version="nexus_capability_plan_v1",
                selected_capabilities=[
                    "codeintel",
                    "memory",
                    "local_model_executor",
                    "swarm",
                    "artifact_gate",
                    "claim_gate",
                    "delivery_gate",
                ],
                required_capabilities=["codeintel", "local_model_executor"],
                optional_capabilities=[],
                conditional_capabilities=[],
                pending_capabilities=[],
                forbidden_capabilities=[],
                constraints=[],
                decision_trace=[],
                replan_trace=[],
                score=1.0,
                signal_snapshot={"route_truth_source": "CapabilityPlanner"},
            )

    req = UnifiedRuntimeRequest(
        task_id="p2-evidence-001",
        workspace_revision="rev-p2",
        task_statement="scan impact risk codeintel with local model executor",
        task_type="codeintel",
        route={
            "recommended_flow": "hybrid",
            "injected_transport": True,
            "online_policy": "auto",
            "mainchain_entry": True,
            "local_enabled": True,
        },
        online_enabled=True,
        local_enabled=True,
        online_prompt="task",
        codeintel={"scan_report_present": True, "risk_score": 6, "impacted_files_count": 1},
        local_request={
            "task_id": "p2-evidence-001",
            "action": "candidate",
            "planner_snapshot": {
                "route_truth_source": "CapabilityPlanner",
                "executor_provider": "ollama",
                "executor_model": "qwen2.5-coder:7b-instruct",
                "model_call_allowed": True,
                "execution_topology": "local_only",
            },
        },
    )
    receipt = UnifiedRuntime(planner=_LocalPlanner(), local_service=local).run(
        req,
        online_invoker=_online,
        verifier=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"v:{c['task_id']}"],
        },
        learning=lambda c: {
            "task_id": c["task_id"],
            "invoked": True,
            "gate_passed": True,
            "evidence_refs": [f"l:{c['task_id']}"],
        },
    )

    bundle = receipt["capability_evidence_bundle"]
    assert bundle["schema"] == "nexus.capability_evidence_bundle.v1"
    assert bundle["immutable"] is True
    assert bundle["planner_decision_id"] == receipt["planner_decision_id"]
    assert bundle["baseline_hash"]
    assert bundle["summary"]["stub_does_not_count_as_success"] is True
    assert bundle["summary"]["selected_not_executed_not_success"] is True
    # memory now has physical get_executor path — may count as real success
    memory_entry = next(e for e in bundle["entries"] if e["name"] == "memory")
    assert memory_entry["invoked_stub"] is False
    # swarm escalate skip not success when untriggered
    swarm_entry = next(e for e in bundle["entries"] if e["name"] == "swarm")
    assert swarm_entry["success"] is False
    assert swarm_entry["skipped"] is True

    # Stage order: evidence before local
    names = [s["name"] for s in receipt["stages"]]
    assert names.index("shared_capability_evidence") < names.index("local")
    assert names.index("local") < names.index("online")

    # Online saw same baseline
    assert _online.last_baseline == bundle["baseline_hash"]
    assert assert_same_baseline(
        bundle=bundle, observed_baseline_hash=_online.last_baseline
    )["ok"]
    # Local planner_snapshot carried baseline
    assert local.seen_baseline == bundle["baseline_hash"]
    assert receipt["context_trace"]["baseline_hash"] == bundle["baseline_hash"]
    assert receipt["public_claim_allowed"] is False if "public_claim_allowed" in receipt else True
    assert receipt["claim_boundary"]["public_claim_allowed"] is False


def test_p2_bundle_builder_rejects_stub_as_success() -> None:
    bundle = build_capability_evidence_bundle(
        task_id="t1",
        workspace_revision="r1",
        task_statement="hello",
        plan_payload={"selected_capabilities": ["memory"]},
        plan_hash="abc",
        planner_decision_id="abc",
        capability_results={
            "memory": {
                "invoked": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["capability:memory:t1:stub"],
                "response": {"stub": True},
            }
        },
        selected_capabilities=["memory"],
    )
    assert bundle["summary"]["real_success_count"] == 0
    assert "memory" in bundle["summary"]["stub_invoked"]
    assert all(not e["success"] for e in bundle["entries"] if e["name"] == "memory")


def test_p2_verify_blocks_tamper_and_immutable_alone_insufficient() -> None:
    """Negative controls: any entry/evidence/source/plan/decision tamper fail-closed."""
    bundle = build_capability_evidence_bundle(
        task_id="t-seal",
        workspace_revision="r1",
        task_statement="seal me",
        plan_payload={"selected_capabilities": ["codeintel", "memory"]},
        plan_hash="plan-seal",
        planner_decision_id="plan-seal",
        capability_results={
            "codeintel": {
                "invoked": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["capability:codeintel:t-seal:real"],
                "physical_callable": "codeintel.scan",
                "response": {},
            },
            "memory": {
                "invoked": True,
                "status": "SUCCEEDED",
                "evidence_refs": ["capability:memory:t-seal:stub"],
                "physical_callable": "stub",
                "response": {"stub": True},
            },
        },
        selected_capabilities=["codeintel", "memory"],
        source_hash="src-aaa",
    )
    ok = verify_capability_evidence_bundle(bundle)
    assert ok["ok"] is True
    assert ok["immutable_alone_insufficient"] is True
    assert bundle["bundle_hash"] == compute_bundle_hash(bundle)

    # immutable alone is not proof
    bare = {"immutable": True, "schema": bundle["schema"]}
    bare_v = verify_capability_evidence_bundle(bare)
    assert bare_v["ok"] is False

    # modify entry success (flip real success off while keeping old hash)
    tampered = dict(bundle)
    tampered["entries"] = [dict(e) for e in bundle["entries"]]
    tampered["entries"][0] = dict(
        tampered["entries"][0], success=False, status="FORGED_FAIL"
    )
    # keep old hash → mismatch
    assert verify_capability_evidence_bundle(tampered)["ok"] is False

    # modify evidence ref
    t2 = dict(bundle)
    t2["entries"] = [dict(e) for e in bundle["entries"]]
    t2["entries"][0] = dict(
        t2["entries"][0],
        evidence_refs=["forged"],
        evidence_ids=["forged"],
    )
    assert verify_capability_evidence_bundle(t2)["ok"] is False

    # modify source hash
    t3 = dict(bundle)
    t3["source_hash"] = "forged-source"
    assert verify_capability_evidence_bundle(t3)["ok"] is False

    # delete selected capability entry
    t4 = dict(bundle)
    t4["entries"] = [e for e in bundle["entries"] if e["name"] != "memory"]
    t4_v = verify_capability_evidence_bundle(t4)
    assert t4_v["ok"] is False
    assert any("missing_selected_entry:memory" in b for b in t4_v["blockers"])

    # wrong planner decision id
    t5 = dict(bundle)
    t5["planner_decision_id"] = "other-decision"
    assert verify_capability_evidence_bundle(t5)["ok"] is False

    # empty consumed_evidence_ids ⇒ not consumed
    cons = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=[],
        selected_capabilities=["codeintel"],
    )
    assert cons["capability_consumed"] is False
    cons_on = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=["capability:codeintel:t-seal:real"],
        selected_capabilities=["codeintel"],
    )
    assert cons_on["capability_consumed"] is True
    # toggling capability changes consumer_input_hash
    cons_off = record_consumption(
        bundle=bundle,
        consumer="Online",
        consumed_evidence_ids=["capability:codeintel:t-seal:real"],
        selected_capabilities=[],
    )
    assert cons_on["consumer_input_hash"] != cons_off["consumer_input_hash"]


def test_p2_selected_not_executed_is_not_success() -> None:
    """Drive a real SELECTED_NOT_EXECUTED-shaped stage entry through the shipped builder."""
    bundle = build_capability_evidence_bundle(
        task_id="t-sne",
        workspace_revision="r1",
        task_statement="hello",
        plan_payload={"selected_capabilities": ["codeintel"]},
        plan_hash="plan-sne",
        planner_decision_id="plan-sne",
        capability_results={
            "codeintel": {
                "invoked": False,
                "status": "SELECTED_NOT_EXECUTED",
                "gate_passed": False,
                "evidence_refs": [],
                "reason": "planner_selected_no_runtime_executor",
                "response": {},
            }
        },
        selected_capabilities=["codeintel"],
    )
    entry = next(e for e in bundle["entries"] if e["name"] == "codeintel")
    assert entry["status"] == "SELECTED_NOT_EXECUTED"
    assert entry["success"] is False
    assert entry["invoked_real"] is False
    assert entry["invoked_stub"] is False
    assert "codeintel" in bundle["summary"]["failed_or_not_executed"]
    assert bundle["summary"]["real_success_count"] == 0
    # Flag is documentation of the rule; the entry above is the behavioral proof.
    assert bundle["summary"]["selected_not_executed_not_success"] is True
