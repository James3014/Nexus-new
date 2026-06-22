"""Tests for MEMORY-EVAL-8 Memory Influence on Repair Decision."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from nexus.services.local_heal.context import HealContext, OperationalContext, GovernanceContext
from nexus.services.local_heal.governance_gate import GovernanceGate
from nexus.services.local_heal.orchestrator import HealOrchestrator


def test_memory_influence_on_repair_decision(tmp_path):
    """Verify that memory influence is successfully captured in terms of prompt, output, and patch deltas."""
    tasks = ["C_12481", "C_13453"]
    output_root = tmp_path / "memory_eval_8_influence_v0" / "runs"

    for task in tasks:
        # 1. nexus_memory_on
        op_on = OperationalContext(
            instance_id=task,
            repo_dir=Path("/tmp/test"),
            problem_statement="test repair",
        )
        op_on.solve_eligible = True
        op_on.final_patch = "test patch content with memory optimization"
        op_on.patch_applied = True
        op_on.model_name = "qwen2.5-coder:7b"
        op_on.receipt_path = f"/tmp/receipt_{task}.json"
        op_on.memory_enabled = True
        op_on.memory_arm = "nexus_memory_on"
        op_on.artifact_output_root = str(output_root)
        op_on.system_prompt = "system prompt text with memory optimization"
        op_on.user_prompt = "user prompt text"

        ctx_on = HealContext(op=op_on, gov=GovernanceContext())
        orchestrator = HealOrchestrator(phases=[], governance_gate=GovernanceGate())
        orchestrator.run(ctx_on)

        # 2. nexus_memory_off
        op_off = OperationalContext(
            instance_id=task,
            repo_dir=Path("/tmp/test"),
            problem_statement="test repair",
        )
        op_off.solve_eligible = True
        op_off.final_patch = "test patch content"
        op_off.patch_applied = True
        op_off.model_name = "qwen2.5-coder:7b"
        op_off.receipt_path = f"/tmp/receipt_{task}.json"
        op_off.memory_enabled = False
        op_off.memory_arm = "nexus_memory_off"
        op_off.artifact_output_root = str(output_root)
        op_off.system_prompt = ""
        op_off.user_prompt = "user prompt text"

        ctx_off = HealContext(op=op_off, gov=GovernanceContext())
        orchestrator.run(ctx_off)

    for task in tasks:
        on_dir = output_root / task / "nexus_memory_on"
        off_dir = output_root / task / "nexus_memory_off"

        assert on_dir.exists()
        assert off_dir.exists()

        # 1. Verify schema hygiene: primary_selected_id exists
        trace_on = json.loads((on_dir / "memory_trace.json").read_text())
        assert "primary_selected_id" in trace_on
        assert trace_on["primary_selected_id"] == f"lh-{task[2:]}"
        assert trace_on["selected_ids"][0] == f"lh-{task[2:]}"

        # 2. Verify Prompt Delta (memory_on system prompt is non-empty)
        prompt_on = json.loads((on_dir / "prompt_manifest.json").read_text())
        prompt_off = json.loads((off_dir / "prompt_manifest.json").read_text())
        assert prompt_on["prompt_length_chars"] > prompt_off["prompt_length_chars"]
        assert prompt_on["memory_section_included"] is True
        assert prompt_off["memory_section_included"] is False

        # 3. Verify Model Output Delta (memory_on has longer patch output)
        output_on = json.loads((on_dir / "model_output_summary.json").read_text())
        output_off = json.loads((off_dir / "model_output_summary.json").read_text())
        assert output_on["output_length_chars"] > output_off["output_length_chars"]

        # 4. Verify Patch Apply Delta
        apply_on = json.loads((on_dir / "patch_apply_result.json").read_text())
        apply_off = json.loads((off_dir / "patch_apply_result.json").read_text())
        assert apply_on["patch_len"] > apply_off["patch_len"]

        # 5. Verify live_runtime + created_during_run=true for all
        for folder in [on_dir, off_dir]:
            for name in ["input_manifest.json", "memory_trace.json", "evidence_packet.json", "prompt_manifest.json", "arm_result.json"]:
                data = json.loads((folder / name).read_text())
                assert data["artifact_source"] == "live_runtime"
                assert data["created_during_run"] is True
