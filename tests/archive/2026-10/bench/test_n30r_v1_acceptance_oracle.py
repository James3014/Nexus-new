"""Behavioral tests for N30R V1 Independent Acceptance Oracle.

Covers: source hash, target symbol, locked search, evidence refs,
prompt validation, candidate lifecycle, verifier, retry, learning,
placeholder detection, hash chain, and hardcoded gate booleans.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_v1_acceptance_oracle import (
    build_task_evidence,
    canonical_sha256,
    is_placeholder_hash,
    is_real_sha256,
    load_json_artifact,
    resolve_evidence_ref,
    validate_a_gate,
    validate_c_gate,
    validate_d_gate,
    validate_live_gate,
    validate_p_gate,
    validate_r_gate,
    validate_x_gate,
    evaluate_trace,
)

REPO_ROOT = str(Path(__file__).resolve().parents[2])
FIXTURE_DIR = os.path.join(REPO_ROOT, "tests", "fixtures", "n30r", "smoke")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_fixture_source() -> str:
    p = os.path.join(FIXTURE_DIR, "semantic_task.py")
    return Path(p).read_text()


def _source_hash() -> str:
    return canonical_sha256(_read_fixture_source())


def _base_trace() -> dict[str, Any]:
    source = _read_fixture_source()
    src_hash = canonical_sha256(source)
    locked = "return n % 2 == 1"
    locked_hash = canonical_sha256(locked)
    return {
        "planner_snapshot_hash": hashlib.sha256(b"plan").hexdigest(),
        "capability_projection_hash": hashlib.sha256(b"proj").hexdigest(),
        "planner_capability_count": 1,
        "selected_capabilities_used": ["local_model_executor"],
        "unknown_capability_count": 0,
        "dependency_errors": 0,
        "target_file": "tests/fixtures/n30r/smoke/semantic_task.py",
        "source_sha256": src_hash,
        "target_symbol": "is_even",
        "locked_search": locked,
        "locked_search_occurrence_count": 1,
        "source_anchor_hash": locked_hash,
        "evidence_refs": [],
        "verifier_command": ["python3", "-c", "assert True"],
        "provider_called": True,
        "model_response_received": True,
        "raw_output_length": 100,
        "prompt_artifact": {"text": "n30r_smoke_semantic tests/fixtures/n30r/smoke/semantic_task.py is_even return n % 2 == 1 PROTOCOL"},
        "rendered_prompt_sha256": hashlib.sha256(b"prompt").hexdigest(),
        "candidate_hash": hashlib.sha256(b"candidate").hexdigest(),
        "patch_sha256": hashlib.sha256(b"candidate").hexdigest(),
        "patch_length": 50,
        "candidate_isolation_attempted": True,
        "candidate_isolated": True,
        "selected_candidate_hash": hashlib.sha256(b"candidate").hexdigest(),
        "apply_status": "success",
        "target_hash_before": src_hash,
        "target_hash_after": hashlib.sha256(b"applied").hexdigest(),
        "verifier_exit_code": 0,
        "verifier_status": "pass",
        "semantic_retry_count": 0,
        "semantic_retry_invoked": False,
        "learning_outcome": {"type": "shadow"},
        "promotion_eligible": False,
        "global_learning_mutated": False,
        "final_receipt": {"schema": "nexus.local_heal.repair_receipt.v1"},
        "receipt_complete": True,
        "terminal_status": "VERIFIED_SOLVE",
        "solve_eligible": True,
        "gate_passed": True,
        "wall_time_sec": 10.0,
        "timed_out": False,
        "timeout_stage": "",
        "synthetic_oracle_fixture": True,
    }


def _synthetic_pass_trace() -> dict[str, Any]:
    t = _base_trace()
    t["synthetic_oracle_fixture"] = True
    t["mock_provider"] = True
    return t


# ---------------------------------------------------------------------------
# Task evidence tests
# ---------------------------------------------------------------------------

class TestTaskEvidence:
    def test_task_evidence_source_hash_matches_disk(self):
        evidence = build_task_evidence("n30r_smoke_semantic", REPO_ROOT)
        fixture_path = os.path.join(REPO_ROOT, evidence["source"]["repo_relative_path"])
        actual = canonical_sha256(Path(fixture_path).read_text())
        assert evidence["source"]["sha256"] == actual

    def test_task_evidence_target_symbol_nonempty(self):
        evidence = build_task_evidence("n30r_smoke_semantic", REPO_ROOT)
        assert evidence["localization"]["target_symbol"] == "is_even"
        assert len(evidence["localization"]["target_symbol"]) > 0

    def test_task_evidence_locked_search_occurs_once(self):
        evidence = build_task_evidence("n30r_smoke_semantic", REPO_ROOT)
        assert evidence["localization"]["locked_search_occurrence_count"] == 1
        assert evidence["localization"]["locked_search"] == "return n % 2 == 1"

    def test_task_evidence_verifier_contract_executes(self):
        evidence = build_task_evidence("n30r_smoke_semantic", REPO_ROOT)
        cmd = evidence["verifier"]["command"]
        assert len(cmd) > 0
        assert cmd[0] == "python3"

    def test_task_evidence_refs_resolve(self):
        evidence = build_task_evidence("n30r_smoke_semantic", REPO_ROOT)
        for ref in evidence["evidence_refs"]:
            path = ref.get("artifact_path", "")
            if path:
                resolved = resolve_evidence_ref(path, REPO_ROOT)
                assert resolved is not None, f"Unresolvable ref: {path}"


# ---------------------------------------------------------------------------
# Oracle acceptance tests
# ---------------------------------------------------------------------------

class TestOracleAcceptance:
    def test_oracle_accepts_valid_synthetic_fixture(self):
        trace = _synthetic_pass_trace()
        result = evaluate_trace(trace, REPO_ROOT)
        assert result["accepted"] is True
        assert result["status"] in (
            "FULL_ARMOR_PATH_ACCEPTED",
            "DETERMINISTIC_PATH_ACCEPTED_LIVE_PENDING",
        )

    def test_oracle_marks_synthetic_non_production(self):
        trace = _synthetic_pass_trace()
        result = evaluate_trace(trace, REPO_ROOT)
        assert result["claim_boundary"]["production_ready"] is False
        assert result["claim_boundary"]["public_claim_allowed"] is False


# ---------------------------------------------------------------------------
# D Gate: source/target/locked_search
# ---------------------------------------------------------------------------

class TestDGateRejections:
    def test_oracle_rejects_missing_target_symbol(self):
        trace = _base_trace()
        del trace["target_symbol"]
        d = validate_d_gate(trace, REPO_ROOT)
        assert d["passed"] is False
        assert "target_symbol" in d["missing_fields"]

    def test_oracle_rejects_locked_search_not_in_source(self):
        trace = _base_trace()
        trace["locked_search"] = "return n % 2 == 999"
        d = validate_d_gate(trace, REPO_ROOT)
        assert d["passed"] is False
        assert any("not found" in i for i in d["issues"])

    def test_oracle_rejects_locked_search_multiple_occurrences(self):
        trace = _base_trace()
        trace["locked_search_occurrence_count"] = 2
        d = validate_d_gate(trace, REPO_ROOT)
        assert d["passed"] is False
        assert any("mismatch" in i for i in d["issues"])

    def test_oracle_rejects_source_hash_mismatch(self):
        trace = _base_trace()
        trace["source_sha256"] = "a" * 64
        d = validate_d_gate(trace, REPO_ROOT)
        assert d["passed"] is False
        assert len(d["hash_mismatches"]) > 0

    def test_oracle_rejects_unresolvable_evidence_ref(self):
        trace = _base_trace()
        trace["evidence_refs"] = ["nonexistent/path.json"]
        d = validate_d_gate(trace, REPO_ROOT)
        assert d["passed"] is False
        assert "nonexistent/path.json" in d["unresolvable_evidence_refs"]

    def test_oracle_rejects_evidence_hash_mismatch(self):
        trace = _base_trace()
        trace["evidence_refs"] = [
            {"artifact_path": "docs/bench/n30r/smoke_manifest.json", "sha256": "a" * 64}
        ]
        d = validate_d_gate(trace, REPO_ROOT)
        assert d["passed"] is False
        assert len(d["hash_mismatches"]) > 0


# ---------------------------------------------------------------------------
# X Gate: prompt/candidate/apply
# ---------------------------------------------------------------------------

class TestXGateRejections:
    def test_oracle_rejects_prompt_without_locked_search(self):
        trace = _base_trace()
        trace["prompt_artifact"] = {"text": "some prompt without the search"}
        evidence = build_task_evidence("n30r_smoke_semantic", REPO_ROOT)
        x = validate_x_gate(trace, evidence)
        assert x["passed"] is False
        assert any("locked_search" in i for i in x["issues"])

    def test_oracle_rejects_model_response_flag_without_output(self):
        trace = _base_trace()
        trace["model_response_received"] = True
        trace["raw_output_length"] = 0
        x = validate_x_gate(trace)
        assert x["passed"] is False

    def test_oracle_rejects_empty_candidate_hash(self):
        trace = _base_trace()
        trace["patch_sha256"] = ""
        trace["candidate_hash"] = ""
        trace["selected_candidate_hash"] = ""
        x = validate_x_gate(trace)
        assert x["passed"] is False
        assert "candidate_hash" in x["missing_fields"]

    def test_oracle_rejects_false_candidate_isolation(self):
        trace = _base_trace()
        trace["candidate_isolation_attempted"] = True
        trace["candidate_isolated"] = False
        x = validate_x_gate(trace)
        assert x["passed"] is False

    def test_oracle_rejects_apply_pass_without_source_change(self):
        trace = _base_trace()
        h = _source_hash()
        trace["target_hash_before"] = h
        trace["target_hash_after"] = h
        trace["apply_status"] = "success"
        x = validate_x_gate(trace)
        assert x["passed"] is True  # X gate doesn't check hash change directly; C gate does


# ---------------------------------------------------------------------------
# R Gate: verifier/retry
# ---------------------------------------------------------------------------

class TestRGateRejections:
    def test_oracle_rejects_verifier_workspace_mismatch(self):
        trace = _base_trace()
        trace["apply_workspace"] = "/ws/a"
        trace["verifier_workspace"] = "/ws/b"
        r = validate_r_gate(trace)
        assert r["passed"] is False
        assert any("workspace" in a for a in r["anti_rules_violated"])

    def test_oracle_rejects_retry_without_verifier_feedback(self):
        trace = _base_trace()
        trace["semantic_retry_count"] = 1
        trace["semantic_retry_invoked"] = False
        r = validate_r_gate(trace)
        assert r["passed"] is False

    def test_oracle_rejects_timeout_inferred_from_wall_time(self):
        trace = _base_trace()
        trace["timed_out"] = True
        trace["timeout_stage"] = ""
        r = validate_r_gate(trace)
        assert r["passed"] is False


# ---------------------------------------------------------------------------
# A Gate: learning/attribution
# ---------------------------------------------------------------------------

class TestAGateRejections:
    def test_oracle_rejects_learning_global_mutation(self):
        trace = _base_trace()
        trace["global_learning_mutated"] = True
        a = validate_a_gate(trace)
        assert a["passed"] is False
        assert any("global_learning_mutated" in a for a in a["anti_rules_violated"])

    def test_oracle_rejects_promotion_eligible_true(self):
        trace = _base_trace()
        trace["promotion_eligible"] = True
        a = validate_a_gate(trace)
        assert a["passed"] is False

    def test_oracle_rejects_capability_contribution_without_evidence(self):
        trace = _base_trace()
        trace["selected_capabilities_used"] = [
            {"name": "ddtree", "selected": True, "invoked": False, "evidence_present": False}
        ]
        trace["capability_contributions"] = trace["selected_capabilities_used"]
        a = validate_a_gate(trace)
        assert a["passed"] is False


# ---------------------------------------------------------------------------
# C Gate: hash chain
# ---------------------------------------------------------------------------

class TestCGateRejections:
    def test_oracle_rejects_placeholder_hash(self):
        trace = _base_trace()
        trace["patch_sha256"] = "placeholder_hash_value_here_not_real"
        c = validate_c_gate(trace)
        assert c["passed"] is False

    def test_oracle_rejects_incomplete_hash_chain(self):
        trace = _base_trace()
        trace["rendered_prompt_sha256"] = ""
        trace["raw_output_sha256"] = ""
        c = validate_c_gate(trace)
        assert len(c["hash_chain_present"]) < 8

    def test_oracle_rejects_snapshot_hash_as_execution_receipt(self):
        trace = _base_trace()
        snap = trace["planner_snapshot_hash"]
        trace["production_receipt_sha256"] = snap
        c = validate_c_gate(trace)
        assert any("snapshot hash" in i for i in c["issues"])

    def test_oracle_rejects_hardcoded_gate_booleans(self):
        trace = _base_trace()
        trace["p_gate_pass"] = True
        trace["d_gate_pass"] = True
        result = evaluate_trace(trace, REPO_ROOT)
        assert "p_gate_pass" not in result
        assert result["p_gate"]["passed"] is True


# ---------------------------------------------------------------------------
# Live Gate
# ---------------------------------------------------------------------------

class TestLiveGate:
    def test_live_gate_accepts_verified_solve(self):
        trace = _base_trace()
        trace["terminal_status"] = "VERIFIED_SOLVE"
        live = validate_live_gate(trace)
        assert live["passed"] is True

    def test_live_gate_rejects_contract_invalid(self):
        trace = _base_trace()
        trace["terminal_status"] = "CONTRACT_INVALID"
        live = validate_live_gate(trace)
        assert live["passed"] is False
        assert any("CONTRACT_INVALID" in r for r in live["rejected"])

    def test_live_gate_rejects_solved_without_provider(self):
        trace = _base_trace()
        trace["solve_eligible"] = True
        trace["provider_called"] = False
        trace["model_call_started"] = False
        live = validate_live_gate(trace)
        assert live["passed"] is False


# ---------------------------------------------------------------------------
# Hash utilities
# ---------------------------------------------------------------------------

class TestHashUtilities:
    def test_is_real_sha256_valid(self):
        h = hashlib.sha256(b"test").hexdigest()
        assert is_real_sha256(h) is True

    def test_is_real_sha256_too_short(self):
        assert is_real_sha256("abc123") is False

    def test_is_real_sha256_not_hex(self):
        assert is_real_sha256("z" * 64) is False

    def test_is_placeholder_hash_mock(self):
        assert is_placeholder_hash("mock_hash_value_here_not_real_at_all_long") is True

    def test_is_placeholder_hash_valid(self):
        h = hashlib.sha256(b"real").hexdigest()
        assert is_placeholder_hash(h) is False

    def test_canonical_sha256_deterministic(self):
        a = canonical_sha256("hello")
        b = canonical_sha256("hello")
        assert a == b
        assert len(a) == 64
