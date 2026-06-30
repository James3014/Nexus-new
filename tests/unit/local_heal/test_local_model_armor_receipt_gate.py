from __future__ import annotations

from nexus.services.local_heal.local_model_armor_receipt_gate import (
    validate_local_model_armor_metadata,
    validate_capability_causality,
)


def _good_metadata():
    return {
        "execution_topology": "local_committee_only",
        "selected_capabilities_used": ["ddtree", "autoreason"],
        "protocol_mode": "anchored_edit",
        "protocol_normalization": {"protocol_used": "solid_search_replace", "normalized": True},
        "source_anchor_present": True,
        "source_anchor_source": "locked_search",
        "source_anchor_hash": "abc123",
        "target_file": "pkg/mod.py",
        "target_symbol": "func",
        "locked_search_present": True,
        "failure_feedback_present": False,
        "final_authority": "NexusVerifier",
        "committee_candidate_count": 3,
        "selected_by": "candidate_policy",
    }


def test_valid_metadata_passes():
    ok, missing = validate_local_model_armor_metadata(_good_metadata())
    assert ok is True
    assert missing == []


def test_missing_execution_topology_fails():
    m = _good_metadata()
    del m["execution_topology"]
    ok, missing = validate_local_model_armor_metadata(m)
    assert ok is False
    assert "execution_topology" in missing


def test_wrong_final_authority_fails():
    m = _good_metadata()
    m["final_authority"] = "LocalModel"
    ok, missing = validate_local_model_armor_metadata(m)
    assert ok is False
    assert "final_authority_not_nexus_verifier" in missing


def test_missing_source_anchor_hash_fails():
    m = _good_metadata()
    m["source_anchor_hash"] = ""
    ok, missing = validate_local_model_armor_metadata(m)
    assert ok is False
    assert "source_anchor_hash_empty" in missing


def test_committee_missing_candidate_count_fails():
    m = _good_metadata()
    del m["committee_candidate_count"]
    ok, missing = validate_local_model_armor_metadata(m)
    assert ok is False
    assert "committee_candidate_count_missing" in missing


def test_committee_missing_selected_by_fails():
    m = _good_metadata()
    del m["selected_by"]
    ok, missing = validate_local_model_armor_metadata(m)
    assert ok is False
    assert "selected_by_missing" in missing


def test_source_anchor_false_needs_reason():
    m = _good_metadata()
    m["source_anchor_present"] = False
    m.pop("source_anchor_missing", None)
    m.pop("localization_missing", None)
    ok, missing = validate_local_model_armor_metadata(m)
    assert ok is False
    assert "source_anchor_missing_reason_absent" in missing


def test_source_anchor_false_with_reason_passes():
    m = _good_metadata()
    m["source_anchor_present"] = False
    m["source_anchor_missing"] = True
    ok, missing = validate_local_model_armor_metadata(m)
    assert ok is True


# --- Causality tests ---

def test_causality_empty_selected_passes():
    ok, issues = validate_capability_causality({})
    assert ok is True


def test_causality_ddtree_selected_not_invoked_fails():
    m = _good_metadata()
    m["selected_capabilities_used"] = ["ddtree", "autoreason"]
    m["ddtree_result"] = {"invoked": False, "failure_reason": "no_candidates"}
    m["autoreason_result"] = {"invoked": True}
    ok, issues = validate_capability_causality(m)
    assert ok is False
    assert "ddtree_selected_but_not_invoked" in issues


def test_causality_ddtree_selected_invoked_passes():
    m = _good_metadata()
    m["selected_capabilities_used"] = ["ddtree"]
    m["ddtree_result"] = {"invoked": True, "gate_passed": True}
    ok, issues = validate_capability_causality(m)
    assert ok is True


def test_causality_autoreason_selected_not_invoked_fails():
    m = _good_metadata()
    m["selected_capabilities_used"] = ["autoreason"]
    m["autoreason_result"] = {"invoked": False}
    ok, issues = validate_capability_causality(m)
    assert ok is False
    assert "autoreason_selected_but_not_invoked" in issues


def test_causality_gate_selected_not_invoked_fails():
    m = _good_metadata()
    m["selected_capabilities_used"] = ["artifact_gate"]
    m["gate_results"] = {"artifact_gate": {"invoked": False}}
    ok, issues = validate_capability_causality(m)
    assert ok is False
    assert "artifact_gate_selected_but_not_invoked" in issues


def test_causality_external_only_ignored():
    m = _good_metadata()
    m["selected_capabilities_used"] = ["swarm_multi_agent", "drone"]
    ok, issues = validate_capability_causality(m)
    assert ok is True


# --- C9.3 Path A causality tests ---

def test_path_a_availability_only_fails_causality():
    m = _good_metadata()
    m["execution_topology"] = "localheal_pipeline"
    m["localheal_pipeline_actual_execution"] = False
    m["localheal_pipeline_availability_only"] = True
    ok, issues = validate_capability_causality(m)
    assert ok is False
    assert "localheal_pipeline_availability_only" in issues


def test_path_a_no_actual_execution_fails_causality():
    m = _good_metadata()
    m["execution_topology"] = "localheal_pipeline"
    m["localheal_pipeline_actual_execution"] = False
    m["localheal_pipeline_availability_only"] = False
    ok, issues = validate_capability_causality(m)
    assert ok is False
    assert "path_a_actual_execution_missing" in issues


def test_path_a_actual_execution_passes_causality():
    m = _good_metadata()
    m["selected_capabilities_used"] = ["ddtree", "autoreason", "repair_loop"]
    m["execution_topology"] = "localheal_pipeline"
    m["localheal_pipeline_actual_execution"] = True
    m["localheal_pipeline_availability_only"] = False
    m["ddtree_result"] = {"invoked": True}
    m["autoreason_result"] = {"invoked": True}
    ok, issues = validate_capability_causality(m)
    assert ok is True


def test_repair_loop_selected_requires_actual_execution():
    m = _good_metadata()
    m["selected_capabilities_used"] = ["repair_loop"]
    m["localheal_pipeline_actual_execution"] = False
    m["localheal_pipeline_availability_only"] = True
    ok, issues = validate_capability_causality(m)
    assert ok is False
    assert "localheal_pipeline_availability_only" in issues


def test_local_committee_only_does_not_require_path_a():
    m = _good_metadata()
    m["execution_topology"] = "local_committee_only"
    m["selected_capabilities_used"] = ["ddtree", "autoreason"]
    m["ddtree_result"] = {"invoked": True}
    m["autoreason_result"] = {"invoked": True}
    ok, issues = validate_capability_causality(m)
    assert ok is True
