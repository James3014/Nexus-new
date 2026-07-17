"""Phase 0: machine-enforced execution contracts for 57 CapabilityPlanner nodes.

gap_class is derived from the execution contract. Unresolved MISSING_ENGINE
nodes are listed honestly (no label-green).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from nexus.engine.capability_planner import default_capability_nodes
from nexus.services.capability_registry import (
    CONSUMER_EFFECTS,
    EXECUTION_CLASSES,
    LOCAL_STAGE_CAPABILITIES,
    PLANNER_EXECUTION_CONTRACTS,
    PROBE_ONLY_REASON_CODES,
    REAL_EXECUTION_CLASSES,
    REQUIRED_EXECUTION_CONTRACT_FIELDS,
    WIRED_REAL,
    build_wiring_matrix,
    classify_gap,
    gap_class_from_execution_class,
    get_execution_contract,
    list_execution_contract_ids,
    list_planner_capability_names,
)
from nexus.services.mainchain_route_freeze import build_capability_catalog


def test_planner_contract_set_equals_57() -> None:
    planner = set(list_planner_capability_names())
    contracts = set(list_execution_contract_ids())
    nodes = set(default_capability_nodes().keys())
    assert len(planner) == 57
    assert len(contracts) == 57
    assert planner == contracts == nodes
    assert set(PLANNER_EXECUTION_CONTRACTS.keys()) == planner


def test_every_contract_has_required_fields_and_enums() -> None:
    for name in list_planner_capability_names():
        c = get_execution_contract(name)
        assert c is not None, name
        for field in REQUIRED_EXECUTION_CONTRACT_FIELDS:
            assert field in c, (name, field)
        assert c["canonical_id"] == name
        assert c["execution_class"] in EXECUTION_CLASSES
        assert c["consumer_effect"] in CONSUMER_EFFECTS
        assert c["public_claim_allowed"] is False
        assert isinstance(c["provider_authorization_required"], bool)
        assert c["positive_control_id"]
        assert c["negative_control_id"]
        assert isinstance(c["required_context_fields"], list)
        assert isinstance(c["success_fields"], list)
        assert isinstance(c["failure_fields"], list)
        assert isinstance(c["consumer_targets"], list)
        assert c["execution_kind"] in {
            "PHYSICAL_EFFECT",
            "CONTROL_EFFECT",
            "EXTERNAL_EFFECT",
            "NONPROMOTED",
            "MISSING",
        }
        assert isinstance(c["required_outcome_fields"], list)
        assert isinstance(c["required_evidence_fields"], list)
        assert c["success_predicate"]


def test_gap_class_derived_from_execution_class() -> None:
    for name, c in PLANNER_EXECUTION_CONTRACTS.items():
        expected = gap_class_from_execution_class(str(c["execution_class"]))
        assert classify_gap(name) == expected, (name, c["execution_class"], classify_gap(name))


def test_wired_real_is_derived_view_of_real_contracts() -> None:
    derived = {
        n
        for n, c in PLANNER_EXECUTION_CONTRACTS.items()
        if c["execution_class"] in REAL_EXECUTION_CLASSES
        and n not in LOCAL_STAGE_CAPABILITIES
    }
    assert set(WIRED_REAL) == derived
    for name in WIRED_REAL:
        assert classify_gap(name) == "F_wired_ok"


def test_missing_engine_not_hidden_as_e_escalate() -> None:
    """MISSING_ENGINE must map to A_missing_invoker (never hidden as E).

    After Phase 3 binds, promotable MISSING_ENGINE may be zero — that is success.
    """
    missing = [
        n
        for n, c in PLANNER_EXECUTION_CONTRACTS.items()
        if c["execution_class"] == "MISSING_ENGINE"
    ]
    for name in missing:
        assert classify_gap(name) == "A_missing_invoker", name
        row = next(r for r in build_wiring_matrix()["rows"] if r["name"] == name)
        assert row["gap_class"] == "A_missing_invoker"
        assert row["execution_class"] == "MISSING_ENGINE"
    # No name may claim F while classified MISSING_ENGINE
    for name, c in PLANNER_EXECUTION_CONTRACTS.items():
        if c["execution_class"] == "MISSING_ENGINE":
            assert classify_gap(name) != "F_wired_ok"


def test_probe_only_reason_codes_remain_e_not_f() -> None:
    matrix = build_wiring_matrix()
    by_name = {r["name"]: r for r in matrix["rows"]}
    for name, reason in PROBE_ONLY_REASON_CODES.items():
        assert name in by_name
        assert classify_gap(name) == "E_escalate_ok"
        assert by_name[name]["reason_code"] == reason
        assert by_name[name]["gap_class"] == "E_escalate_ok"
        assert by_name[name]["execution_class"] not in REAL_EXECUTION_CLASSES


def test_wiring_matrix_exposes_execution_contract_projection() -> None:
    matrix = build_wiring_matrix()
    assert matrix["node_count"] == 57
    assert matrix["contract_count"] == 57
    assert matrix["routing_surface_changed"] is False
    assert "execution_class_counts" in matrix
    assert sum(matrix["execution_class_counts"].values()) == 57
    f_count = matrix["gap_class_counts"]["F_wired_ok"]
    assert matrix["physical_runtime_eligible"] == f_count
    # Honest floor: Phase 0 baseline 17; Phase 2+ may promote hardened nodes.
    assert f_count >= 17
    assert f_count < 91
    for row in matrix["rows"]:
        assert row["public_claim_allowed"] is False
        assert row["execution_class"] in EXECUTION_CLASSES


def test_catalog_denominators_91_77_14_unchanged() -> None:
    root = Path(__file__).resolve().parents[2]
    catalog = build_capability_catalog(repo_root=root)
    assert catalog["planner_node_count"] == 57
    assert catalog["canonical_union_count"] == 91
    assert catalog["canonical_row_count"] == 77
    assert catalog["alias_row_count"] == 14
    assert catalog["union_accounted_count"] == 91
    assert catalog["union_unaccounted_count"] == 0
    assert catalog["alias_validation"]["ok"] is True
    assert catalog["alias_validation"]["alias_count"] == 14
    assert catalog["routing_surface_changed"] is False
    assert catalog["selection_authority"] == "CapabilityPlanner"


def test_local_online_projection_covers_all_57() -> None:
    from nexus.services.capability_registry import (
        LOCAL_EXECUTION_MODES,
        ONLINE_EXECUTION_MODES,
        build_local_online_contract_projection,
        project_local_execution_mode,
        project_online_execution_mode,
    )

    proj = build_local_online_contract_projection()
    assert proj["planner_contract_count"] == 57
    assert proj["independent_local_truth"] is False
    assert sum(proj["local_mode_counts"].values()) == 57
    assert sum(proj["online_mode_counts"].values()) == 57
    for row in proj["rows"]:
        assert row["local_mode"] in LOCAL_EXECUTION_MODES
        assert row["online_mode"] in ONLINE_EXECUTION_MODES
        assert row["public_claim_allowed"] is False
        assert project_local_execution_mode(row["canonical_id"]) == row["local_mode"]
        assert project_online_execution_mode(row["canonical_id"]) == row["online_mode"]

    by_name = {row["canonical_id"]: row for row in proj["rows"]}
    assert by_name["local_model_executor"]["local_mode"] == "EXECUTE_HERE"
    assert by_name["local_model_executor"]["online_mode"] == "NOT_TARGET"
    assert by_name["external_doc_scout"]["local_mode"] == "EXTERNAL_NOT_LOCAL"
    assert (
        by_name["external_doc_scout"]["online_mode"]
        == "EXTERNAL_AUTHORIZED_EXECUTE"
    )
    assert by_name["codeintel"]["local_mode"] == "CONSUME_SHARED_EVIDENCE"
    assert by_name["codeintel"]["online_mode"] == "CONSUME_SHARED_EVIDENCE"


def test_online_production_context_exposes_contract_derived_consumer_modes() -> None:
    from nexus.services.online_nexus_context import build_online_nexus_context

    ctx = build_online_nexus_context(
        task_statement="target-specific contract projection",
        task_id="consumer-targets-1",
        plan={
            "selected_capabilities": [
                "codeintel",
                "local_model_executor",
                "external_doc_scout",
            ],
            "plan_hash": "plan-consumer-targets-1",
        },
    )

    modes = ctx.lineage["consumer_execution_modes"]
    assert modes == {
        "codeintel": "CONSUME_SHARED_EVIDENCE",
        "local_model_executor": "NOT_TARGET",
        "external_doc_scout": "EXTERNAL_AUTHORIZED_EXECUTE",
    }
    assert ctx.lineage["consumer_contract_source"].endswith(
        "PLANNER_EXECUTION_CONTRACTS"
    )


def test_promotable_missing_engine_is_zero() -> None:
    from nexus.services.capability_registry import (
        EXECUTION_CLASS_MISSING_ENGINE,
        _node_meta,
    )

    promotable_missing = [
        n
        for n, c in PLANNER_EXECUTION_CONTRACTS.items()
        if c["execution_class"] == EXECUTION_CLASS_MISSING_ENGINE
        and _node_meta(n)["maturity"].lower()
        in {"production", "beta", "routed", "active", "ga"}
    ]
    assert promotable_missing == []


def test_phase0_unresolved_list_is_reportable() -> None:
    """Phase 0 may list unresolved names; do not re-label them F to green."""
    unresolved = sorted(
        n
        for n, c in PLANNER_EXECUTION_CONTRACTS.items()
        if c["execution_class"] == "MISSING_ENGINE"
        or (
            c["execution_class"] not in REAL_EXECUTION_CLASSES
            and str(c.get("reason_code") or "").endswith("_not_production")
        )
        or str(c.get("reason_code") or "")
        in {
            "shallow_should_run_only",
            "shallow_health_check_only",
            "escalate_probe_or_unavailable",
            "route_probe_not_production_execute",
            "requires_model_execution_boundary",
            "skill_probe_not_production",
            "scheduler_probe_not_production",
            "resume_probe_not_production",
            "sensor_probe_not_production",
        }
    )
    # Unresolved may shrink as engines are bound; never claim F while unresolved.
    assert len(unresolved) >= 1
    for name in unresolved:
        assert classify_gap(name) != "F_wired_ok", name
    counts = Counter(
        PLANNER_EXECUTION_CONTRACTS[n]["execution_class"] for n in unresolved
    )
    assert sum(counts.values()) == len(unresolved)
