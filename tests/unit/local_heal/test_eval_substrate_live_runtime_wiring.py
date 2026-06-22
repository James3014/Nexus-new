"""Tests for EVAL-SUBSTRATE-1C runtime wiring proof."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.live_artifact_collector import LiveArtifactCollector
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.interface import RepairPlan
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator


def _make_minimal_ctx(task_id: str = "C_12481") -> HealContext:
    """Create minimal HealContext for testing."""
    op = OperationalContext(
        instance_id=task_id,
        repo_dir=Path("/tmp/test"),
        problem_statement="test repair",
    )
    op.solve_eligible = True
    op.final_patch = "test patch content"
    op.patch_applied = True
    op.model_name = "qwen2.5-coder:7b"
    op.receipt_path = "/tmp/receipt.json"

    gov = GovernanceContext()
    return HealContext(op=op, gov=gov)


class TestRuntimeWiringProof:
    """Test that runtime path (not direct hook call) invokes collector."""

    def test_run_calls_finalize_which_calls_collector(self):
        """HealOrchestrator.run() -> _finalize_run -> _attach_live_full_loop_artifacts -> collector."""
        ctx = _make_minimal_ctx("C_12481")

        # Create orchestrator with empty phases (run will call _finalize_run in finally)
        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )

        # Call run() - the runtime-facing path
        result_ctx = orchestrator.run(ctx)

        # Verify collector was attached by runtime path
        assert hasattr(result_ctx.op, "_live_artifact_collector"), \
            "Collector not attached - runtime path did not invoke _attach_live_full_loop_artifacts"
        collector = result_ctx.op._live_artifact_collector
        assert isinstance(collector, LiveArtifactCollector)
        assert collector.get_total_count() == 11

    def test_run_produces_all_11_artifacts(self, tmp_path):
        """Runtime path produces all 11 required artifacts."""
        ctx = _make_minimal_ctx("C_12481")

        # Override output dir for test
        original_init = LiveArtifactCollector.__init__
        def patched_init(self, task_id, arm, output_dir):
            original_init(self, task_id, arm, tmp_path)
        LiveArtifactCollector.__init__ = patched_init

        try:
            orchestrator = HealOrchestrator(
                phases=[],
                governance_gate=GovernanceGate(),
            )
            orchestrator.run(ctx)

            task_dir = tmp_path / "C_12481" / "nexus_memory_on"
            assert task_dir.exists()

            required_files = [
                "input_manifest.json", "memory_trace.json", "evidence_packet.json",
                "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                "verifier_result.json", "receipt.json", "evidence_bundle.json",
                "bottleneck_classification.json", "arm_result.json",
            ]
            for f in required_files:
                assert (task_dir / f).exists(), f"Missing: {f}"
        finally:
            LiveArtifactCollector.__init__ = original_init

    def test_all_artifacts_have_repair_attempt_id(self, tmp_path):
        """All artifacts from runtime path share repair_attempt_id."""
        ctx = _make_minimal_ctx("C_12481")

        original_init = LiveArtifactCollector.__init__
        def patched_init(self, task_id, arm, output_dir):
            original_init(self, task_id, arm, tmp_path)
        LiveArtifactCollector.__init__ = patched_init

        try:
            orchestrator = HealOrchestrator(
                phases=[],
                governance_gate=GovernanceGate(),
            )
            orchestrator.run(ctx)

            task_dir = tmp_path / "C_12481" / "nexus_memory_on"
            for f in ["input_manifest.json", "memory_trace.json", "evidence_packet.json",
                       "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                       "verifier_result.json", "receipt.json", "evidence_bundle.json",
                       "bottleneck_classification.json", "arm_result.json"]:
                with open(task_dir / f) as fh:
                    data = json.load(fh)
                assert "repair_attempt_id" in data, f"Missing repair_attempt_id in {f}"
                assert data["repair_attempt_id"] == "C_12481"
        finally:
            LiveArtifactCollector.__init__ = original_init

    def test_verifier_consistent_with_arm_result(self, tmp_path):
        """arm_result.solved=true requires verifier_result.status=PASS."""
        ctx = _make_minimal_ctx("C_12481")

        original_init = LiveArtifactCollector.__init__
        def patched_init(self, task_id, arm, output_dir):
            original_init(self, task_id, arm, tmp_path)
        LiveArtifactCollector.__init__ = patched_init

        try:
            orchestrator = HealOrchestrator(
                phases=[],
                governance_gate=GovernanceGate(),
            )
            orchestrator.run(ctx)

            task_dir = tmp_path / "C_12481" / "nexus_memory_on"
            with open(task_dir / "verifier_result.json") as f:
                verifier = json.load(f)
            with open(task_dir / "arm_result.json") as f:
                arm = json.load(f)

            if arm["solved"]:
                assert verifier["status"] == "PASS"
        finally:
            LiveArtifactCollector.__init__ = original_init

    def test_all_artifacts_live_runtime(self, tmp_path):
        """All artifacts from runtime path are labeled live_runtime."""
        ctx = _make_minimal_ctx("C_12481")

        original_init = LiveArtifactCollector.__init__
        def patched_init(self, task_id, arm, output_dir):
            original_init(self, task_id, arm, tmp_path)
        LiveArtifactCollector.__init__ = patched_init

        try:
            orchestrator = HealOrchestrator(
                phases=[],
                governance_gate=GovernanceGate(),
            )
            orchestrator.run(ctx)

            task_dir = tmp_path / "C_12481" / "nexus_memory_on"
            for f in ["input_manifest.json", "memory_trace.json", "evidence_packet.json",
                       "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                       "verifier_result.json", "receipt.json", "evidence_bundle.json",
                       "bottleneck_classification.json", "arm_result.json"]:
                with open(task_dir / f) as fh:
                    data = json.load(fh)
                assert data.get("artifact_source") == "live_runtime", \
                    f"Artifact {f} not live_runtime: {data.get('artifact_source')}"
        finally:
            LiveArtifactCollector.__init__ = original_init
