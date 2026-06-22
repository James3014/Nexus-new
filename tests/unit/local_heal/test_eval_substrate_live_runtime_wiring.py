"""Tests for EVAL-SUBSTRATE-1B runtime wiring with fresh output isolation."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator


def _make_ctx(task_id: str, output_root: Path, memory_enabled: bool = True) -> HealContext:
    """Create HealContext with configurable output root."""
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
    op.memory_enabled = memory_enabled
    op.artifact_output_root = str(output_root)

    gov = GovernanceContext()
    return HealContext(op=op, gov=gov)


class TestRuntimeWiringProof:
    """Test that runtime path invokes collector through orchestrator.run()."""

    def test_run_produces_all_11_artifacts(self, tmp_path):
        """Runtime path produces all 11 required artifacts."""
        output_root = tmp_path / "runs"
        ctx = _make_ctx("C_12481", output_root, memory_enabled=True)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        # Arm is determined by memory trace status, not memory_enabled flag
        collector = ctx.op._live_artifact_collector
        task_dir = Path(str(collector.output_dir))
        assert task_dir.exists()

        required_files = [
            "input_manifest.json", "memory_trace.json", "evidence_packet.json",
            "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
            "verifier_result.json", "receipt.json", "evidence_bundle.json",
            "bottleneck_classification.json", "arm_result.json",
        ]
        for f in required_files:
            assert (task_dir / f).exists(), f"Missing: {f}"

    def test_all_artifacts_have_repair_attempt_id(self, tmp_path):
        """All artifacts from runtime path share repair_attempt_id."""
        output_root = tmp_path / "runs"
        ctx = _make_ctx("C_12481", output_root, memory_enabled=True)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        collector = ctx.op._live_artifact_collector
        task_dir = Path(str(collector.output_dir))
        for f in ["input_manifest.json", "memory_trace.json", "evidence_packet.json",
                   "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                   "verifier_result.json", "receipt.json", "evidence_bundle.json",
                   "bottleneck_classification.json", "arm_result.json"]:
            with open(task_dir / f) as fh:
                data = json.load(fh)
            assert "repair_attempt_id" in data, f"Missing repair_attempt_id in {f}"
            assert data["repair_attempt_id"] == "C_12481"

    def test_verifier_consistent_with_arm_result(self, tmp_path):
        """arm_result.solved=true requires verifier_result.status=PASS."""
        output_root = tmp_path / "runs"
        ctx = _make_ctx("C_12481", output_root, memory_enabled=True)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        collector = ctx.op._live_artifact_collector
        task_dir = Path(str(collector.output_dir))
        with open(task_dir / "verifier_result.json") as f:
            verifier = json.load(f)
        with open(task_dir / "arm_result.json") as f:
            arm = json.load(f)

        if arm["solved"]:
            assert verifier["status"] == "PASS"

    def test_all_artifacts_live_runtime(self, tmp_path):
        """All artifacts from runtime path are labeled live_runtime."""
        output_root = tmp_path / "runs"
        ctx = _make_ctx("C_12481", output_root, memory_enabled=True)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        collector = ctx.op._live_artifact_collector
        task_dir = Path(str(collector.output_dir))
        for f in ["input_manifest.json", "memory_trace.json", "evidence_packet.json",
                   "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                   "verifier_result.json", "receipt.json", "evidence_bundle.json",
                   "bottleneck_classification.json", "arm_result.json"]:
            with open(task_dir / f) as fh:
                data = json.load(fh)
            assert data.get("artifact_source") == "live_runtime", \
                f"Artifact {f} not live_runtime: {data.get('artifact_source')}"

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
