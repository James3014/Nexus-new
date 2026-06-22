"""Tests for EVAL-SUBSTRATE-1 live full-loop artifact capture."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector


class TestLiveArtifactCollector:
    def test_collector_creates_all_artifacts(self, tmp_path):
        """Collector creates all 11 required artifacts."""
        collector = LiveArtifactCollector("C_12481", "nexus_memory_on", tmp_path)
        collector.capture_input_manifest("C_12481", "sympy", "test", "single_anchor")
        collector.capture_memory_trace({"available": True})
        collector.capture_evidence_packet({"nodes": 5})
        collector.capture_prompt_manifest({"length": 100})
        collector.capture_model_output({"patch_produced": True})
        collector.capture_patch_apply({"patch_applied": True})
        collector.capture_verifier_result({"status": "PASS"})
        collector.capture_receipt({"gate_passed": True})
        collector.capture_evidence_bundle({"task_id": "C_12481"})
        collector.capture_bottleneck({"final_status": "SOLVED"})
        collector.capture_arm_result({"solved": True})

        assert collector.get_total_count() == 11

    def test_all_artifacts_are_live_runtime(self, tmp_path):
        """All artifacts from collector are labeled live_runtime."""
        collector = LiveArtifactCollector("C_12481", "nexus_memory_on", tmp_path)
        collector.capture_input_manifest("C_12481", "sympy", "test", "single_anchor")
        collector.capture_memory_trace({"available": True})
        collector.capture_evidence_packet({"nodes": 5})
        collector.capture_prompt_manifest({"length": 100})
        collector.capture_model_output({"patch_produced": True})
        collector.capture_patch_apply({"patch_applied": True})
        collector.capture_verifier_result({"status": "PASS"})
        collector.capture_receipt({"gate_passed": True})
        collector.capture_evidence_bundle({"task_id": "C_12481"})
        collector.capture_bottleneck({"final_status": "SOLVED"})
        collector.capture_arm_result({"solved": True})

        assert collector.get_live_count() == 11

    def test_write_all_produces_files(self, tmp_path):
        """Collector writes all files to disk."""
        collector = LiveArtifactCollector("C_12481", "nexus_memory_on", tmp_path)
        collector.capture_input_manifest("C_12481", "sympy", "test", "single_anchor")
        collector.capture_memory_trace({"available": True})
        collector.capture_evidence_packet({"nodes": 5})
        collector.capture_prompt_manifest({"length": 100})
        collector.capture_model_output({"patch_produced": True})
        collector.capture_patch_apply({"patch_applied": True})
        collector.capture_verifier_result({"status": "PASS"})
        collector.capture_receipt({"gate_passed": True})
        collector.capture_evidence_bundle({"task_id": "C_12481"})
        collector.capture_bottleneck({"final_status": "SOLVED"})
        collector.capture_arm_result({"solved": True})

        collector.write_all()

        task_dir = tmp_path / "C_12481" / "nexus_memory_on"
        assert task_dir.exists()
        assert (task_dir / "input_manifest.json").exists()
        assert (task_dir / "memory_trace.json").exists()
        assert (task_dir / "evidence_packet.json").exists()
        assert (task_dir / "prompt_manifest.json").exists()
        assert (task_dir / "model_output_summary.json").exists()
        assert (task_dir / "patch_apply_result.json").exists()
        assert (task_dir / "verifier_result.json").exists()
        assert (task_dir / "receipt.json").exists()
        assert (task_dir / "evidence_bundle.json").exists()
        assert (task_dir / "bottleneck_classification.json").exists()
        assert (task_dir / "arm_result.json").exists()

    def test_all_files_share_repair_attempt_id(self, tmp_path):
        """All written files share the same repair_attempt_id."""
        collector = LiveArtifactCollector("C_12481", "nexus_memory_on", tmp_path)
        collector.capture_input_manifest("C_12481", "sympy", "test", "single_anchor")
        collector.capture_memory_trace({"available": True})
        collector.capture_evidence_packet({"nodes": 5})
        collector.capture_prompt_manifest({"length": 100})
        collector.capture_model_output({"patch_produced": True})
        collector.capture_patch_apply({"patch_applied": True})
        collector.capture_verifier_result({"status": "PASS"})
        collector.capture_receipt({"gate_passed": True})
        collector.capture_evidence_bundle({"task_id": "C_12481"})
        collector.capture_bottleneck({"final_status": "SOLVED"})
        collector.capture_arm_result({"solved": True})

        collector.write_all()

        task_dir = tmp_path / "C_12481" / "nexus_memory_on"
        for artifact_name in ["input_manifest.json", "memory_trace.json", "evidence_packet.json",
                              "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                              "verifier_result.json", "receipt.json", "evidence_bundle.json",
                              "bottleneck_classification.json", "arm_result.json"]:
            with open(task_dir / artifact_name) as f:
                data = json.load(f)
            assert data.get("repair_attempt_id") == "C_12481", f"Missing repair_attempt_id in {artifact_name}"

    def test_verifier_consistent_with_arm_result(self, tmp_path):
        """arm_result.solved=true requires verifier_result.status=PASS."""
        collector = LiveArtifactCollector("test", "arm", tmp_path)
        collector.capture_verifier_result({"status": "PASS"})
        collector.capture_arm_result({"solved": True, "verifier_status": "PASS"})

        collector.write_all()
        task_dir = tmp_path / "test" / "arm"

        with open(task_dir / "verifier_result.json") as f:
            verifier = json.load(f)
        with open(task_dir / "arm_result.json") as f:
            arm = json.load(f)

        if arm["solved"]:
            assert verifier["status"] == "PASS"

    def test_fixture_backed_not_live(self, tmp_path):
        """Fixture-backed artifacts cannot be classified as LIVE_FULL_LOOP_READY."""
        collector = LiveArtifactCollector("test", "arm", tmp_path)
        # Manually create a fixture-backed artifact
        collector.artifacts.append(type('obj', (object,), {
            'artifact_name': 'test.json',
            'artifact_source': 'fixture_backed',
            'created_during_run': False,
            'source_component': 'test',
            'source_timestamp': '',
            'data': {},
        })())

        live_count = collector.get_live_count()
        total_count = collector.get_total_count()
        assert live_count == 0
        assert total_count == 1
        # Cannot be FULL_LOOP_READY with fixture-backed artifacts
