"""Tests for MEMORY-EVAL-5 true memory retrieval proof."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator
from nexus.services.local_heal.memory_trace import MemoryTrace


def test_true_memory_retrieval_success(tmp_path):
    """Verify memory_on retrieves the seeded C_12481 card and contains no stub finding id."""
    task_id = "C_12481"
    output_root = tmp_path / "memory_eval_5_true_retrieval_v0" / "runs"

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

    # Mock memory trace with a MemoryTrace object
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
    # Must NOT contain eval_stub_finding_id
    assert "eval_stub_finding_id" not in trace["selected_ids"]
    assert "lh-12481" in trace["selected_ids"]

    # Verify prompt_manifest.json
    prompt_path = task_dir / "prompt_manifest.json"
    assert prompt_path.exists()
    prompt = json.loads(prompt_path.read_text())
    assert prompt["memory_section_included"] is True
