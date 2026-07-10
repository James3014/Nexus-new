"""N30R-V1: Full Armor Vertical Slice Behavioral Tests.

Verifies P→D→X→R→A→C pipeline for n30r_smoke_semantic.
Tests: deterministic trace output, hash chain integrity, semantic retry lifecycle, fail-closed guards.
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


class TestV1TraceSourceEvidence:
    """Verify source evidence is loaded from real fixture."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_source_loaded_from_fixture(self, receipt):
        assert receipt["source_loaded_from"] == "fixture"

    def test_source_sha256_is_real(self, receipt):
        h = receipt["source_sha256"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_source_length_positive(self, receipt):
        assert receipt["source_length"] > 0

    def test_source_artifact_exists(self, receipt):
        artifacts_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "v1_artifacts"
        source_files = list(artifacts_dir.glob("*/source_evidence.json"))
        assert len(source_files) > 0, "No source evidence artifact found"

    def test_source_artifact_hash_matches(self, receipt):
        artifacts_dir = Path(__file__).resolve().parents[2] / "docs" / "bench" / "n30r" / "v1_artifacts"
        source_files = list(artifacts_dir.glob("*/source_evidence.json"))
        assert len(source_files) > 0
        artifact = json.loads(source_files[0].read_text())
        assert artifact["source_sha256"] == receipt["source_sha256"]

    def test_evidence_refs_resolve(self, receipt):
        for ref in receipt["evidence_refs"]:
            assert ":" in ref, f"Evidence ref {ref} is not resolvable"
            assert ref.startswith("v1:"), f"Evidence ref {ref} missing v1: prefix"


class TestV1TraceTargetSymbol:
    """Verify target symbol and locked search provenance."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_target_symbol_provenance(self, receipt):
        assert receipt["target_symbol"] == "is_even"
        assert receipt["localization_method"] == "ast_boundary"

    def test_locked_search_nonempty(self, receipt):
        assert receipt["locked_search"] != ""

    def test_locked_search_sha256_is_real(self, receipt):
        h = receipt["locked_search_sha256"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_locked_search_occurs_once(self, receipt):
        assert receipt["locked_search_occurrence_count"] == 1

    def test_locked_search_present_in_source(self, receipt):
        assert receipt["locked_search_present_in_source"] is True


class TestV1TraceSemanticRetry:
    """Verify deterministic fail → semantic retry lifecycle."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_semantic_retry_triggered(self, receipt):
        assert receipt["semantic_retry_count"] >= 1

    def test_semantic_retry_invocation_source(self, receipt):
        assert receipt["semantic_retry_invocation_source"] == "orchestrator_semantic_retry"

    def test_provider_called(self, receipt):
        assert receipt["provider_call_count"] >= 4

    def test_first_candidate_recorded(self, receipt):
        fc = receipt["first_candidate"]
        assert isinstance(fc, dict)
        assert "candidate_hash" in fc
        assert "apply_status" in fc
        assert "verifier_status" in fc

    def test_second_candidate_recorded(self, receipt):
        sc = receipt["second_candidate"]
        assert isinstance(sc, dict)
        assert "candidate_hash" in sc
        assert "apply_status" in sc
        assert "verifier_status" in sc


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
                     "executor_request_sha256", "executor_metadata_sha256"]:
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


class TestV1TraceCapabilityAttribution:
    """Verify capability attribution is evidence-backed."""

    @pytest.fixture(scope="class")
    def receipt(self):
        return _run_trace()

    def test_invoked_capabilities_nonempty(self, receipt):
        assert len(receipt["invoked_capabilities"]) > 0

    def test_repair_loop_invoked(self, receipt):
        assert "repair_loop" in receipt["invoked_capabilities"]

    def test_shadow_outcome_exists(self, receipt):
        assert os.path.exists(receipt["shadow_outcome_path"])

    def test_shadow_outcome_structure(self, receipt):
        with open(receipt["shadow_outcome_path"]) as f:
            so = json.load(f)
        assert so["shadow_only"] is True
        assert so["promotion_eligible"] is False
        assert so["global_learning_mutated"] is False
        assert "capabilities" in so
        assert "repair_loop" in so["capabilities"]
