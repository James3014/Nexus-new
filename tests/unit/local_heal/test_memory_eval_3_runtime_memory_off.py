"""Tests for MEMORY-EVAL-3 runtime memory-off arm."""
from __future__ import annotations

import json
import pytest
import shutil
from pathlib import Path
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator


RUNS_BASE = Path("artifacts/runtime/eval_substrate_1b_runtime_wiring_v0/runs")


def _make_ctx_with_memory_disabled(task_id: str = "C_12481") -> HealContext:
    """Create HealContext with memory_enabled=False for memory_off arm."""
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

    gov = GovernanceContext()
    return HealContext(op=op, gov=gov)


class TestRuntimeMemoryOff:
    """Test that memory_off path produces live artifacts through runtime."""

    def test_memory_off_path_through_run(self):
        """HealOrchestrator.run() with memory_enabled=False produces artifacts."""
        task_id = "BMEVAL3_TEST"
        ctx = _make_ctx_with_memory_disabled(task_id)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        # Verify collector was attached
        assert hasattr(ctx.op, "_live_artifact_collector")
        collector = ctx.op._live_artifact_collector
        assert collector.get_total_count() == 11

        # Verify memory trace is TRACE_MISSING (memory disabled)
        mem_trace = getattr(ctx.op, "_memory_influence_trace", None)
        assert mem_trace is not None
        assert mem_trace.trace_status == "TRACE_MISSING"

        # Verify artifacts have artifact_source=live_runtime
        task_dir = RUNS_BASE / task_id / "nexus_memory_off"
        for f in ["input_manifest.json", "memory_trace.json", "evidence_packet.json",
                   "prompt_manifest.json", "model_output_summary.json", "patch_apply_result.json",
                   "verifier_result.json", "receipt.json", "evidence_bundle.json",
                   "bottleneck_classification.json", "arm_result.json"]:
            assert (task_dir / f).exists(), f"Missing: {f}"
            with open(task_dir / f) as fh:
                data = json.load(fh)
            assert data.get("artifact_source") == "live_runtime", f"Missing artifact_source in {f}"
            assert data.get("created_during_run") is True, f"Missing created_during_run in {f}"

    def test_memory_off_prompt_excludes_memory(self):
        """memory_off prompt_manifest shows memory_section_included=false."""
        task_id = "BMEVAL3_PROMPT"
        ctx = _make_ctx_with_memory_disabled(task_id)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        task_dir = RUNS_BASE / task_id / "nexus_memory_off"
        with open(task_dir / "prompt_manifest.json") as f:
            data = json.load(f)
        assert data.get("memory_section_included") is False

    def test_memory_off_trace_status_trace_missing(self):
        """memory_off memory_trace shows trace_status=TRACE_MISSING."""
        task_id = "BMEVAL3_TRACE"
        ctx = _make_ctx_with_memory_disabled(task_id)

        orchestrator = HealOrchestrator(
            phases=[],
            governance_gate=GovernanceGate(),
        )
        orchestrator.run(ctx)

        task_dir = RUNS_BASE / task_id / "nexus_memory_off"
        with open(task_dir / "memory_trace.json") as f:
            data = json.load(f)
        assert data.get("trace_status") == "TRACE_MISSING"
