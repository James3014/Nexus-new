"""Tests for RRL2 Full Repair Loop Evidence Harness."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.evidence_harness import EvidenceHarness, EvidenceBundle


class TestEvidenceBundleSchema:
    def test_bundle_has_all_required_fields(self):
        bundle = EvidenceBundle(task_id="test_task")
        d = bundle.to_dict()
        required = [
            "task_id", "repo", "issue_summary", "task_class", "difficulty",
            "route_selected", "selected_anchor", "memory_available",
            "verifier_status", "final_status", "primary_bottleneck",
        ]
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_bundle_timestamp_set(self):
        bundle = EvidenceBundle(task_id="test", timestamp="2026-01-01T00:00:00")
        assert bundle.timestamp == "2026-01-01T00:00:00"


class TestBottleneckClassification:
    def test_solved_classification(self):
        harness = EvidenceHarness()
        bundle = EvidenceBundle(task_id="test", verifier_status="PASS")
        harness.classify_bottleneck(bundle)
        assert bundle.final_status == "SOLVED"
        assert bundle.primary_bottleneck == "none"

    def test_verifier_fail_evidence_memory(self):
        harness = EvidenceHarness()
        bundle = EvidenceBundle(
            task_id="test",
            verifier_status="FAIL",
            patch_applied=True,
            patch_format_valid=True,
            memory_available=True,
            memory_selected_ids=[],
        )
        harness.classify_bottleneck(bundle)
        assert bundle.final_status == "VERIFIER_FAIL"
        assert bundle.primary_bottleneck == "evidence_memory"

    def test_verifier_fail_patch_format(self):
        harness = EvidenceHarness()
        bundle = EvidenceBundle(
            task_id="test",
            verifier_status="FAIL",
            patch_applied=True,
            patch_format_valid=False,
        )
        harness.classify_bottleneck(bundle)
        assert bundle.final_status == "VERIFIER_FAIL"
        assert bundle.primary_bottleneck == "patch_format"

    def test_model_wrong_classification(self):
        harness = EvidenceHarness()
        bundle = EvidenceBundle(task_id="test", patch_produced=False)
        harness.classify_bottleneck(bundle)
        assert bundle.final_status == "MODEL_WRONG"
        assert bundle.primary_bottleneck == "model_generation"

    def test_patch_apply_fail_classification(self):
        harness = EvidenceHarness()
        bundle = EvidenceBundle(
            task_id="test",
            patch_produced=True,
            patch_applied=False,
        )
        harness.classify_bottleneck(bundle)
        assert bundle.final_status == "PATCH_APPLY_FAIL"
        assert bundle.primary_bottleneck == "patch_apply"


class TestEvidenceHarness:
    def test_start_task(self):
        harness = EvidenceHarness()
        bundle = harness.start_task(task_id="C_12481", repo="sympy")
        assert bundle.task_id == "C_12481"
        assert bundle.repo == "sympy"

    def test_finalize_writes_bundle(self, tmp_path):
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = harness.start_task(task_id="test_task")
        bundle.verifier_status = "PASS"
        bundle.patch_produced = True
        bundle.patch_applied = True

        path = harness.finalize(bundle)
        assert path.exists()

        with open(path) as f:
            data = json.load(f)
        assert data["task_id"] == "test_task"
        assert data["final_status"] == "SOLVED"

    def test_finalize_writes_bottleneck(self, tmp_path):
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle = EvidenceBundle(task_id="test_task")
        bundle.verifier_status = "FAIL"
        bundle.patch_applied = True
        bundle.patch_format_valid = True
        bundle.memory_available = True
        bundle.memory_selected_ids = []

        harness.finalize(bundle)

        bottleneck_path = tmp_path / "test_task" / "bottleneck_classification.json"
        assert bottleneck_path.exists()

        with open(bottleneck_path) as f:
            data = json.load(f)
        assert data["final_status"] == "VERIFIER_FAIL"
        assert data["primary_bottleneck"] == "evidence_memory"

    def test_harness_records_bundles(self, tmp_path):
        harness = EvidenceHarness(output_dir=tmp_path)
        bundle1 = harness.start_task(task_id="t1")
        bundle1.verifier_status = "PASS"
        harness.finalize(bundle1)

        bundle2 = harness.start_task(task_id="t2")
        bundle2.verifier_status = "FAIL"
        harness.finalize(bundle2)

        assert len(harness.bundles) == 2
