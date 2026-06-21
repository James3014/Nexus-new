"""Tests for RRL3 minimal runtime evidence harness integration."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.evidence_harness import EvidenceHarness, EvidenceBundle


class TestEvidenceHarnessRuntimeIntegration:
    """Test that EvidenceHarness can be attached to a real execution path."""

    def test_harness_produces_evidence_bundle(self, tmp_path):
        """Runtime path creates evidence_bundle.json for selected task."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="C_12481", repo="sympy")
        bundle.patch_produced = True
        bundle.patch_applied = True
        bundle.verifier_status = "PASS"
        bundle.route_selected = "full_nexus"
        bundle.model_name = "qwen2.5-coder:7b"

        path = harness.finalize(bundle)
        assert path.exists()

        with open(path) as f:
            data = json.load(f)
        assert data["task_id"] == "C_12481"
        assert data["patch_produced"] is True
        assert data["verifier_status"] == "PASS"

    def test_harness_produces_bottleneck_classification(self, tmp_path):
        """Runtime path creates bottleneck_classification.json for selected task."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="C_12481")
        bundle.verifier_status = "PASS"
        harness.finalize(bundle)

        bottleneck_path = tmp_path / "C_12481" / "bottleneck_classification.json"
        assert bottleneck_path.exists()

        with open(bottleneck_path) as f:
            data = json.load(f)
        assert data["final_status"] == "SOLVED"
        assert data["primary_bottleneck"] == "none"

    def test_harness_does_not_alter_prompt(self, tmp_path):
        """Evidence harness does not alter prompt content."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="test")
        # Prompt fields should remain at defaults
        assert bundle.prompt_length_chars == 0
        assert bundle.memory_section_included is False
        assert bundle.failure_section_included is False

    def test_harness_does_not_alter_verifier(self, tmp_path):
        """Evidence harness does not alter verifier command/status."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="test")
        bundle.verifier_status = "PASS"
        harness.finalize(bundle)
        # Verifier status should be recorded, not altered
        assert bundle.verifier_status == "PASS"

    def test_harness_finalize_is_idempotent(self, tmp_path):
        """Evidence harness finalize writes same path on repeated calls."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="test")
        path1 = harness.finalize(bundle)
        path2 = harness.finalize(bundle)
        # Same path (idempotent write)
        assert path1 == path2
        # File should exist and be valid JSON
        assert path1.exists()
        with open(path1) as f:
            data = json.load(f)
        assert data["task_id"] == "test"

    def test_missing_fields_reported(self, tmp_path):
        """Missing fields are reported, not hidden."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="test")
        path = harness.finalize(bundle)

        with open(path) as f:
            data = json.load(f)

        # Many fields should be empty/default (not populated)
        assert data["repo"] == ""
        assert data["issue_summary"] == ""
        assert data["selected_anchor"] == ""
        assert data["model_name"] == ""

    def test_classification_result_present(self, tmp_path):
        """Classification result is present in evidence bundle."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="test")
        bundle.verifier_status = "FAIL"
        bundle.patch_produced = False
        harness.finalize(bundle)

        with open(str(tmp_path / "test" / "evidence_bundle.json")) as f:
            data = json.load(f)
        assert data["final_status"] == "MODEL_WRONG"
        assert data["primary_bottleneck"] == "model_generation"

    def test_artifact_path_bounded(self, tmp_path):
        """Artifact path is bounded under evidence harness root."""
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="test_task")
        path = harness.finalize(bundle)

        assert str(tmp_path) in str(path)
        assert "test_task" in str(path)
        assert "evidence_bundle.json" in str(path)
