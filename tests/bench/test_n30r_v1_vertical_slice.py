"""N30R-V1: Full Armor Vertical Slice Behavioral Tests.

Verifies P→D→X→R→A→C pipeline for n30r_smoke_semantic.
Tests: deterministic trace output, hash chain integrity, fail-closed guards.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.n30r_runner import _materialize_task


def _run_trace():
    """Import and run the trace generator, returning the receipt dict."""
    from scripts.bench.n30r_v1_full_armor_trace import run_v1_trace
    return run_v1_trace()


class TestV1TracePipelineStages:
    """Verify each stage of P→D→X→R→A→C completes."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_planner_capabilities_present(self, receipt):
        assert len(receipt["planner_capabilities"]) == 8
        assert "repair_loop" in receipt["planner_capabilities"]
        assert "local_model_executor" in receipt["planner_capabilities"]

    def test_executor_capabilities_present(self, receipt):
        assert len(receipt["executor_capabilities"]) == 5
        assert "repair_loop" in receipt["executor_capabilities"]

    def test_planner_to_projection_accounted(self, receipt):
        assert receipt["planner_to_projection_accounted"] is True

    def test_projection_to_executor_match(self, receipt):
        assert receipt["projection_to_executor_match"] is True

    def test_executor_to_pipeline_match(self, receipt):
        assert receipt["executor_to_pipeline_match"] is True

    def test_pipeline_to_receipt_match(self, receipt):
        assert receipt["pipeline_to_receipt_match"] is True

    def test_source_anchor_present(self, receipt):
        assert receipt["source_anchor_present"] is True

    def test_locked_search_present_in_source(self, receipt):
        assert receipt["locked_search_present_in_source"] is True

    def test_target_symbol_is_even(self, receipt):
        assert receipt["target_symbol"] == "is_even"

    def test_target_file_is_f_py(self, receipt):
        assert receipt["target_file"] == "f.py"


class TestV1TraceCandidateAndVerifier:
    """Verify candidate isolation and verifier lifecycle."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_candidate_isolated(self, receipt):
        assert receipt["candidate_isolated"] is True

    def test_candidate_hash_is_real_sha256(self, receipt):
        h = receipt["candidate_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_match(self, receipt):
        assert receipt["hash_match"] is True

    def test_verifier_result_pass(self, receipt):
        assert receipt["verifier_result"] == "pass"

    def test_solved(self, receipt):
        assert receipt["solved"] is True

    def test_armor_receipt_complete(self, receipt):
        assert receipt["armor_receipt_complete"] is True


class TestV1TraceHashChain:
    """Verify hash chain integrity in final receipt."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_planner_snapshot_hash_is_real(self, receipt):
        h = receipt["planner_snapshot_sha256"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_projection_hash_is_real(self, receipt):
        h = receipt["projection_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_evidence_pack_hash_is_real(self, receipt):
        h = receipt["evidence_pack_sha256"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_executor_request_hash_is_real(self, receipt):
        h = receipt["executor_request_sha256"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_no_placeholder_hashes(self, receipt):
        for key in ["planner_snapshot_sha256", "projection_hash", "evidence_pack_sha256",
                     "executor_request_sha256", "executor_metadata_sha256", "candidate_hash"]:
            h = receipt.get(key, "")
            assert h != "", f"{key} is empty"
            assert "placeholder" not in h.lower(), f"{key} contains placeholder"


class TestV1TraceFailClosedGuards:
    """Verify fail-closed behaviors are preserved."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_live_ollama_calls_zero(self, receipt):
        assert receipt["live_ollama_calls"] == 0

    def test_mock_provider_used(self, receipt):
        assert receipt["mock_provider"] is True

    def test_baseline_sha_recorded(self, receipt):
        assert receipt["baseline_sha"] == "958b915f2"

    def test_wall_time_positive(self, receipt):
        assert receipt["wall_time_sec"] > 0


class TestV1TraceDeterministicGate:
    """Deterministic gate must PASS before live 7B."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_target_symbol_nonempty(self, receipt):
        assert receipt["target_symbol"] != ""

    def test_locked_search_valid(self, receipt):
        assert receipt["locked_search_present_in_source"] is True

    def test_source_anchor_valid(self, receipt):
        assert receipt["source_anchor_present"] is True

    def test_candidate_hash_nonempty(self, receipt):
        assert receipt["candidate_hash"] != ""

    def test_candidate_isolated(self, receipt):
        assert receipt["candidate_isolated"] is True

    def test_verifier_pass(self, receipt):
        assert receipt["verifier_result"] == "pass"

    def test_solved(self, receipt):
        assert receipt["solved"] is True
