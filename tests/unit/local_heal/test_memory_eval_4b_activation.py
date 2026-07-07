"""Tests for MEMORY-EVAL-4B runtime memory-on stub injection."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.memory_trace import MemoryTrace


def test_memory_on_stub_injection_writes_to_fresh_root(tmp_path):
    """Verify that when memory_arm=nexus_memory_on, it stub-injects RetrievedLesson and sets prompt_manifest."""
    task_id = "C_12481"
    output_root = tmp_path / "memory_eval_4b_activation_v0" / "runs"

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
    op.memory_enabled = True
    op.memory_arm = "nexus_memory_on"
    op.artifact_output_root = str(output_root)

    # Mock memory trace
    mock_trace = MemoryTrace(
        available=True,
        trace_status="TRACE_AVAILABLE",
        retrieved_count=1,
        selected_ids=["lh-12481"],
        memory_evidence_ids=["lh-12481"],
        provenance_count=1,
        no_memory_match=False,
        verifier_status="PASS",
    )

    def mock_attach_memory(self, ctx):
        ctx.op._memory_influence_trace = mock_trace

    with patch.object(HealOrchestrator, "_attach_memory_influence_trace", mock_attach_memory):
        ctx = HealContext(op=op, gov=GovernanceContext())
        orchestrator = HealOrchestrator(phases=[], governance_gate=GovernanceGate())
        orchestrator.run(ctx)

    task_dir = output_root / task_id / "nexus_memory_on"

    # Verify memory_trace.json
    trace_path = task_dir / "memory_trace.json"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text())
    assert trace["trace_status"] == "TRACE_AVAILABLE"
    assert trace["retrieved_count"] > 0
    # When real lessons exist in store, they are used; otherwise stub is injected
    assert len(trace["selected_ids"]) > 0

    # Verify prompt_manifest.json
    prompt_path = task_dir / "prompt_manifest.json"
    assert prompt_path.exists()
    prompt = json.loads(prompt_path.read_text())
    assert prompt["memory_section_included"] is True

    # Verify arm_result.json
    arm_path = task_dir / "arm_result.json"
    assert arm_path.exists()
    arm = json.loads(arm_path.read_text())
    assert arm["arm"] == "nexus_memory_on"
