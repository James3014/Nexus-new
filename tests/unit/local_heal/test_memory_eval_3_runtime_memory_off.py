"""Tests for MEMORY-EVAL-3B runtime memory-off arm with fresh output isolation."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator


def _make_ctx_with_memory_disabled(task_id: str, output_root: Path) -> HealContext:
    """Create HealContext with memory_enabled=False and explicit output root."""
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
    op.memory_enabled = False
    op.memory_arm = "nexus_memory_off"
    op.artifact_output_root = str(output_root)

    gov = GovernanceContext()
    return HealContext(op=op, gov=gov)


class TestRuntimeMemoryOffFreshOutput:
    """Test that memory_off path writes to fresh output root."""

    def test_memory_off_writes_to_fresh_memory_eval_3_root(self, tmp_path):
        """memory_off path writes 11/11 artifacts to fresh root."""
        task_id = "C_12481"
        output_root = tmp_path / "memory_eval_3_runtime_memory_off_v0" / "runs"

        ctx = _make_ctx_with_memory_disabled(task_id, output_root)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        task_dir = output_root / task_id / "nexus_memory_off"

        required = [
            "input_manifest.json", "memory_trace.json", "evidence_packet.json",
            "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
            "verifier_result.json", "receipt.json", "evidence_bundle.json",
            "bottleneck_classification.json", "arm_result.json",
        ]

        for name in required:
            path = task_dir / name
            assert path.exists(), f"Missing: {name}"
            data = json.loads(path.read_text())
            assert data["artifact_source"] == "live_runtime", f"Wrong artifact_source in {name}"
            assert data["created_during_run"] is True, f"Wrong created_during_run in {name}"
            assert data["repair_attempt_id"] == task_id, f"Wrong repair_attempt_id in {name}"

        prompt = json.loads((task_dir / "prompt_manifest.json").read_text())
        assert prompt["memory_section_included"] is False

        trace = json.loads((task_dir / "memory_trace.json").read_text())
        assert trace["trace_status"] in {"TRACE_MISSING", "NOT_USED"}

        arm = json.loads((task_dir / "arm_result.json").read_text())
        assert arm["arm"] == "nexus_memory_off"

    def test_no_pollution_of_eval_substrate(self, tmp_path):
        """memory_off artifacts do NOT pollute eval_substrate_1b."""
        task_id = "NO_POLLUTION"
        output_root = tmp_path / "isolated_root" / "runs"
        eval_substrate = Path("artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs")

        ctx = _make_ctx_with_memory_disabled(task_id, output_root)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        # Verify output is in isolated root, not eval_substrate
        isolated_dir = output_root / task_id / "nexus_memory_off"
        assert isolated_dir.exists()
        assert (isolated_dir / "input_manifest.json").exists()

        # Verify eval_substrate was NOT modified by this run
        eval_substrate_task = eval_substrate / task_id
        assert not eval_substrate_task.exists(), "Polluted eval_substrate!"
