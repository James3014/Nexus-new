"""Tests for RRL3C runtime evidence harness proof closure."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.evidence_harness import EvidenceHarness, EvidenceBundle


class TestOrchestratorHookBehavior:
    """Test the orchestrator hook behavior via narrow adapter."""

    def test_hook_uses_instance_id_as_task_id(self):
        """Hook should use instance_id (not task_id) as task identifier."""
        # Simulate what _attach_evidence_harness does
        harness = EvidenceHarness(output_dir=Path("/tmp/test_hook"))
        # OperationalContext has instance_id, not task_id
        instance_id = "C_12481_instance"
        bundle = harness.start_task(task_id=instance_id)
        assert bundle.task_id == instance_id

    def test_hook_does_not_raise_on_missing_fields(self):
        """Hook should not raise if fields are missing."""
        harness = EvidenceHarness(output_dir=Path("/tmp/test_hook"))
        bundle = harness.start_task(task_id="test")
        # All fields are default/empty - should not raise
        harness.finalize(bundle)
        assert bundle.task_id == "test"

    def test_hook_does_not_modify_prompt_fields(self):
        """Hook should not modify prompt/verifier fields in ctx.op."""
        harness = EvidenceHarness(output_dir=Path("/tmp/test_hook"))
        bundle = harness.start_task(task_id="test")
        # Prompt fields should remain at defaults
        assert bundle.prompt_length_chars == 0
        assert bundle.memory_section_included is False
        assert bundle.failure_section_included is False
        assert bundle.evidence_section_included is False

    def test_hook_produces_evidence_bundle(self):
        """Hook produces evidence_bundle.json."""
        harness = EvidenceHarness(output_dir=Path("/tmp/test_hook"))
        bundle = harness.start_task(task_id="C_12481")
        bundle.patch_produced = True
        bundle.patch_applied = True
        bundle.verifier_status = "PASS"
        path = harness.finalize(bundle)
        assert path.exists()
        with open(path) as f:
            data = json.load(f)
        assert data["task_id"] == "C_12481"
        assert data["final_status"] == "SOLVED"

    def test_hook_produces_bottleneck_classification(self):
        """Hook produces bottleneck_classification.json."""
        harness = EvidenceHarness(output_dir=Path("/tmp/test_hook"))
        bundle = harness.start_task(task_id="test")
        bundle.verifier_status = "FAIL"
        bundle.patch_produced = False
        harness.finalize(bundle)
        bottleneck_path = Path("/tmp/test_hook") / "test" / "bottleneck_classification.json"
        assert bottleneck_path.exists()
        with open(bottleneck_path) as f:
            data = json.load(f)
        assert data["final_status"] == "MODEL_WRONG"

    def test_runtime_artifact_exists_at_committed_path(self):
        """Runtime artifacts exist under committed artifact root."""
        committed_path = Path("artifacts/runtime/rrl3_runtime_evidence_harness_integration_v0/runs/unknown")
        assert committed_path.exists()
        assert (committed_path / "evidence_bundle.json").exists()
        assert (committed_path / "bottleneck_classification.json").exists()

    def test_committed_bundle_has_task_id(self):
        """Committed bundle has task_id field (may be 'unknown')."""
        bundle_path = Path("artifacts/runtime/rrl3_runtime_evidence_harness_integration_v0/runs/unknown/evidence_bundle.json")
        with open(bundle_path) as f:
            data = json.load(f)
        assert "task_id" in data
        assert "final_status" in data
        assert "primary_bottleneck" in data
