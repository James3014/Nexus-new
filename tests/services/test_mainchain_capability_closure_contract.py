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


def test_gap_class_derived_from_execution_class() -> None:
    for name, c in PLANNER_EXECUTION_CONTRACTS.items():
        expected = gap_class_from_execution_class(str(c["execution_class"]))
        assert classify_gap(name) == expected, (name, c["execution_class"], classify_gap(name))


def test_wired_real_is_derived_view_of_real_contracts() -> None:
    derived = {
        n
        for n, c in PLANNER_EXECUTION_CONTRACTS.items()
        if c["execution_class"] in REAL_EXECUTION_CLASSES
        and n != "local_model_executor"
    }
    assert set(WIRED_REAL) == derived
    for name in WIRED_REAL:
        assert classify_gap(name) == "F_wired_ok"


def test_missing_engine_not_hidden_as_e_escalate() -> None:
    missing = [
        n
        for n, c in PLANNER_EXECUTION_CONTRACTS.items()
        if c["execution_class"] == "MISSING_ENGINE"
    ]
    assert missing, "Phase 0 must still surface unresolved engines honestly"
    for name in missing:
        assert classify_gap(name) == "A_missing_invoker", name
        row = next(r for r in build_wiring_matrix()["rows"] if r["name"] == name)
        assert row["gap_class"] == "A_missing_invoker"
        assert row["execution_class"] == "MISSING_ENGINE"


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
    assert f_count == 17  # honest Phase 0 floor (not inflated)
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
    assert len(unresolved) >= 14
    # No unresolved name may claim F
    for name in unresolved:
        assert classify_gap(name) != "F_wired_ok", name
    counts = Counter(
        PLANNER_EXECUTION_CONTRACTS[n]["execution_class"] for n in unresolved
    )
    assert counts.get("MISSING_ENGINE", 0) >= 1
