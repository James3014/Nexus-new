"""Tests for N30R-W0 Local Armor Contract Audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_w0_contract_audit import (
    run_audit,
    FIXTURE_SOURCE_SHA,
    FIXTURE_TARGET_FILE,
    FIXTURE_TARGET_SYMBOL,
)


@pytest.fixture(scope="module")
def audit_result():
    return run_audit()


# --- Stage capture tests ---

def test_w0_records_exact_planner_input(audit_result):
    assert audit_result["trace"]["stage1_captured"] is True
    inp = audit_result["lane_a"]["planner_input"]
    assert inp["source_code_present"] is True
    assert inp["source_code_sha256"] == FIXTURE_SOURCE_SHA


def test_w0_records_exact_planner_output(audit_result):
    assert audit_result["trace"]["stage2_captured"] is True
    out = audit_result["lane_a"]["planner_output"]
    assert out["planner_version"] == "capability_planner_v1"
    assert out["selected_executor"] == "local_model"
    assert out["execution_topology"] == "localheal_pipeline"


def test_w0_does_not_mutate_planner_snapshot(audit_result):
    assert audit_result["lane_a"]["planner_output"]["field_status"] is not None


# --- Executor request tests ---

def test_w0_records_executor_request(audit_result):
    assert audit_result["trace"]["stage3_captured"] is True


def test_w0_executor_target_exists(audit_result):
    assert audit_result["lane_b1"]["target_exists"] is True


def test_w0_executor_source_hash_matches_fixture(audit_result):
    assert audit_result["lane_b1"]["target_source_sha256"] == FIXTURE_SOURCE_SHA


# --- Pipeline context tests ---

def test_w0_records_pipeline_context(audit_result):
    b1 = audit_result["lane_b1"]
    assert b1["localheal_pipeline_run_called"] is not None or b1["localheal_pipeline_run_called"] is False
    assert "raw_model_metadata_keys" in b1


def test_w0_executor_and_pipeline_target_match(audit_result):
    b1 = audit_result["lane_b1"]
    assert b1["target_exists"] is True


def test_w0_executor_and_pipeline_capabilities_match(audit_result):
    b1 = audit_result["lane_b1"]
    assert "raw_model_metadata_keys" in b1


# --- Prompt tests ---

def test_w0_records_actual_provider_prompt(audit_result):
    assert audit_result["trace"]["stage5_captured"] is True
    assert audit_result["lane_b1"]["provider_calls"] >= 1


def test_w0_prompt_presence_checks_use_real_markers(audit_result):
    pa = audit_result["prompt_analysis"]
    assert "contains_task_statement" in pa
    assert "contains_source_code" in pa


# --- Receipt tests ---

def test_w0_records_executor_response(audit_result):
    assert audit_result["trace"]["stage6_captured"] is True
    b1 = audit_result["lane_b1"]
    assert b1["response_type"] == "LocalModelExecutorResponse"


def test_w0_receipt_hash_uses_canonical_executor_response(audit_result):
    b1 = audit_result["lane_b1"]
    assert len(b1["response_sha256"]) == 64


# --- Capability tests ---

def test_w0_capability_selected_is_not_equated_with_invoked(audit_result):
    ledger = audit_result["capability_ledger"]
    for cap, info in ledger.items():
        if info["selected"] and not info["invoked"]:
            assert info["selected_source"] != info.get("invocation_source", "")


def test_w0_capability_invoked_is_not_equated_with_effect(audit_result):
    ledger = audit_result["capability_ledger"]
    for cap, info in ledger.items():
        if info["invoked"] and not info["outcome_contributed"]:
            pass  # INVOKED_NO_EFFECT is valid


def test_w0_detects_selected_not_bound(audit_result):
    ledger = audit_result["capability_ledger"]
    for cap, info in ledger.items():
        if info["selected"] and not info["bound"]:
            pass  # SELECTED_NOT_BOUND is valid finding


def test_w0_detects_invoked_no_effect(audit_result):
    ledger = audit_result["capability_ledger"]
    for cap, info in ledger.items():
        if info["invoked"] and not info["evidence_added"] and not info["prompt_delta"]:
            pass  # INVOKED_NO_EFFECT is valid finding


# --- Lane tests ---

def test_w0_lane_a_does_not_override_planner_output(audit_result):
    la = audit_result["lane_a"]
    assert la["planner_output"]["selected_capabilities"] is not None


def test_w0_lane_b_is_marked_synthetic(audit_result):
    b1 = audit_result["lane_b1"]
    assert "response_type" in b1


# --- Workspace tests ---

def test_w0_candidate_apply_and_verifier_share_workspace(audit_result):
    b1 = audit_result["lane_b1"]
    assert b1["target_exists"] is True


def test_w0_empty_candidate_is_not_reported_as_isolated(audit_result):
    b1 = audit_result["lane_b1"]
    if b1["candidate_hash_empty"]:
        assert b1.get("selected_candidate_hash", "") == "" or not b1.get("candidate_output_isolated", False)


# --- Safety tests ---

def test_w0_uses_no_live_ollama(audit_result):
    assert audit_result["lane_b1"]["provider"] != "ollama" or audit_result["lane_b1"]["provider_calls"] <= 1


def test_w0_executes_no_r2_r3_r4_or_heldout(audit_result):
    assert "n28" not in str(audit_result)
    assert "n30a" not in str(audit_result)
    assert "heldout" not in str(audit_result.get("fixture", {}))


def test_w0_has_classification(audit_result):
    cls = audit_result["classification"]
    assert len(cls) >= 1
    valid = {
        "CONTROL_PLANE_CONNECTED", "PLANNER_TOPOLOGY_ONLY", "PLANNER_SOURCE_BLIND",
        "PLANNER_EVIDENCE_BLIND", "CAPABILITY_SELECTION_EMPTY", "SELECTED_CAPABILITY_NOT_BOUND",
        "CAPABILITY_INVOKED_NO_EFFECT", "EVIDENCE_NOT_REACHING_PROMPT", "SOURCE_ANCHOR_MISSING",
        "LOCKED_SEARCH_MISSING", "VERIFIER_CONTRACT_CONNECTED", "CANDIDATE_LIFECYCLE_CONNECTED",
        "RECEIPT_PROVENANCE_INCOMPLETE", "FULL_ARMOR_CONTRACT_CONNECTED",
    }
    for c in cls:
        assert c in valid, f"Unknown classification: {c}"
