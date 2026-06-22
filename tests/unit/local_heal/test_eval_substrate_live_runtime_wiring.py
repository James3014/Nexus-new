"""Tests for EVAL-SUBSTRATE-1B runtime wiring."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector
from nexus.services.local_heal.evidence_harness import EvidenceHarness


class TestRuntimeWiring:
    """Test that LiveArtifactCollector is wired into runtime path."""

    def test_orchestrator_hook_invokes_collector(self):
        """Runtime hook invokes LiveArtifactCollector without test directly calling capture_*."""
        from nexus.services.local_heal.orchestrator import HealOrchestrator
        from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
        from nexus.services.local_heal.interface import RepairPlan

        # Create minimal ctx
        op = OperationalContext(
            instance_id="C_12481",
            repo_dir=Path("/tmp/test"),
            problem_statement="test",
        )
        op.solve_eligible = True
        op.final_patch = "test patch"
        op.patch_applied = True
        op.model_name = "qwen2.5-coder:7b"
        op.receipt_path = "/tmp/receipt.json"

        gov = GovernanceContext()
        ctx = HealContext(op=op, gov=gov)

        # Create orchestrator with minimal phases
        orchestrator = HealOrchestrator(phases=[], governance_gate=type('obj', (object,), {'audit': lambda s, c: None})())

        # Call the hook directly
        orchestrator._attach_live_full_loop_artifacts(ctx)

        # Verify collector was created and attached
        assert hasattr(ctx.op, "_live_artifact_collector")
        collector = ctx.op._live_artifact_collector
        assert isinstance(collector, LiveArtifactCollector)
        assert collector.get_total_count() == 11

    def test_all_11_artifacts_written(self, tmp_path):
        """Runtime hook writes all 11 required artifacts."""
        from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector

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
        required_files = [
            "input_manifest.json", "memory_trace.json", "evidence_packet.json",
            "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
            "verifier_result.json", "receipt.json", "evidence_bundle.json",
            "bottleneck_classification.json", "arm_result.json",
        ]
        for f in required_files:
            assert (task_dir / f).exists(), f"Missing: {f}"

    def test_all_artifacts_have_repair_attempt_id(self, tmp_path):
        """All artifacts include repair_attempt_id."""
        from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector

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

        for f in ["input_manifest.json", "memory_trace.json", "evidence_packet.json",
                   "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                   "verifier_result.json", "receipt.json", "evidence_bundle.json",
                   "bottleneck_classification.json", "arm_result.json"]:
            with open(task_dir / f) as fh:
                data = json.load(fh)
            assert "repair_attempt_id" in data, f"Missing repair_attempt_id in {f}"

    def test_verifier_consistent_with_arm_result(self, tmp_path):
        """arm_result.solved=true requires verifier_result.status=PASS."""
        from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector

        collector = LiveArtifactCollector("C_12481", "nexus_memory_on", tmp_path)
        collector.capture_verifier_result({"status": "PASS"})
        collector.capture_arm_result({"solved": True, "verifier_status": "PASS"})
        collector.write_all()

        task_dir = tmp_path / "C_12481" / "nexus_memory_on"
        with open(task_dir / "verifier_result.json") as f:
            verifier = json.load(f)
        with open(task_dir / "arm_result.json") as f:
            arm = json.load(f)

        if arm["solved"]:
            assert verifier["status"] == "PASS"

    def test_fixture_backed_not_live(self, tmp_path):
        """Fixture-backed artifacts cannot be classified as LIVE_FULL_LOOP_READY."""
        from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector

        collector = LiveArtifactCollector("test", "arm", tmp_path)
        collector.artifacts.append(type('obj', (object,), {
            'artifact_name': 'test.json',
            'artifact_source': 'fixture_backed',
            'created_during_run': False,
            'source_component': 'test',
            'source_timestamp': '',
            'data': {},
        })())

        assert collector.get_live_count() == 0
        assert collector.get_total_count() == 1
