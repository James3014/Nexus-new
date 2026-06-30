from __future__ import annotations

from nexus.services.local_heal.local_model_armor_receipt_gate import validate_local_model_armor_metadata


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
