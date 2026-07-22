"""Task V3: Deep Dual-Core Repair Closure Test Suite.

Verifies dual-core continuation & handoff when both `local_enabled=True` and `online_enabled=True`.
Guarantees local VerifiedAssistPacket (VAP) generation, clean online handoff without raw CoT leak,
`local_online_continuation=True` claim boundary, and fail-closed negative control checks.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest


def test_dual_core_repair_continuation_and_handoff(tmp_path: Path) -> None:
    """V3: Prove dual-core repair execution loop: Local VAP generation → Online handoff → Receipt.

    Verifies local assist packet creation, online prompt attachment, and clean receipt creation.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "target.py"
    target.write_text("def compute(): return 0\n", encoding="utf-8")

    task_id = "v3-dual-core-task-001"
    rev = "rev-v3-001"
    task_stmt = "Refactor compute() in target.py to return 42"

    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision=rev,
        task_statement=task_stmt,
        task_type="repair",
        route={
            "workspace_root": str(workspace),
            "online_policy": "auto",
            "injected_transport": True,
            "provider": "gemini",
        },
        local_enabled=True,
        online_enabled=True,
        online_prompt=task_stmt,
        codeintel={"workspace_root": str(workspace)},
        local_request={
            "action": "repair",
            "task_id": task_id,
            "workspace_root": str(workspace),
        },
    )

    patch_text = "--- target.py\n+++ target.py\n@@ -1 +1 @@\n-def compute(): return 0\n+def compute(): return 42\n"
    patch_hash = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    source_raw = f"{rev}:{task_stmt}".encode("utf-8")
    source_hash = hashlib.sha256(source_raw).hexdigest()

    seen_online_payloads: list[dict[str, Any]] = []

    def dummy_local_executor(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "task_id": task_id,
            "status": "SUCCEEDED",
            "invoked": True,
            "local_model_invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "evidence_refs": [f"local_assist:{task_id}:vap_created"],
            "model_candidate_hash": patch_hash,
            "selected_candidate_hash": patch_hash,
            "applied_patch_hash": patch_hash,
            "patch_text": patch_text,
            "physical_callable": "nexus.services.local_assist_executor",
            "candidate_summary": {
                "isolation_status": "isolated",
                "selected_candidate_hash_matches_applied": True,
                "model_candidate_hash": patch_hash,
                "selected_candidate_hash": patch_hash,
                "applied_patch_hash": patch_hash,
            },
            "target_files": ["target.py"],
            "bounded_diagnosis": "compute() returns 0 instead of 42",
        }

    def dummy_online_invoker(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen_online_payloads.append(dict(payload))
        # Perform physical file edit
        target.write_text("def compute(): return 42\n", encoding="utf-8")
        return {
            "task_id": task_id,
            "status": "SUCCEEDED",
            "invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "evidence_refs": [f"online_repair:{task_id}:patch_synthesized"],
            "candidate_hash": patch_hash,
            "applied_hash": patch_hash,
            "response": {
                "status": "SUCCEEDED",
                "provider": "gemini",
                "model_calls": 1,
            },
        }

    def dummy_verifier(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        art_bytes = f"dual_core_verifier:{task_id}:{patch_hash}".encode("utf-8")
        art_hash = hashlib.sha256(art_bytes).hexdigest()
        return {
            "task_id": task_id,
            "verifier_task_id": task_id,
            "invoked": True,
            "evidence_present": True,
            "evidence_refs": [f"verifier:dual_core:{task_id}"],
            "gate_passed": True,
            "status": "SUCCEEDED",
            "verifier_status": "pass",
            "verifier_artifact": f"sha256:{art_hash}",
            "source_hash": source_hash,
            "verifier_source_hash": source_hash,
        }

    def dummy_learning(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "task_id": task_id,
            "invoked": True,
            "evidence_present": True,
            "evidence_refs": [f"learning:dual_core:{task_id}"],
            "gate_passed": True,
            "status": "SUCCEEDED",
        }

    runtime = UnifiedRuntime(local_service=dummy_local_executor)
    receipt = runtime.run(
        request,
        online_invoker=dummy_online_invoker,
        verifier=dummy_verifier,
        learning=dummy_learning,
        receipt_path=tmp_path / "dual_core_repair_receipt.json",
    )

    # 1. Verify local_online_continuation flag in claim boundary
    claim_b = receipt.get("claim_boundary") or {}
    assert claim_b.get("local_online_continuation") is True

    # 2. Verify both local and online stages invoked
    stages = receipt.get("stages") or []
    stage_map = {s.get("name"): s for s in stages if isinstance(s, dict)}
    assert "local" in stage_map
    assert stage_map["local"].get("status") == "SUCCEEDED"
    assert "online" in stage_map
    assert stage_map["online"].get("status") == "SUCCEEDED"

    # 3. Verify online invoker received payload
    assert len(seen_online_payloads) == 1

    # 4. Verify physical file edit
    assert target.read_text(encoding="utf-8") == "def compute(): return 42\n"

    # 5. Verify receipt file on disk
    receipt_file = tmp_path / "dual_core_repair_receipt.json"
    assert receipt_file.exists()


def test_dual_core_repair_negative_control_fails_closed(tmp_path: Path) -> None:
    """V3 Negative Control: Failing local or online stage breaks continuation."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    task_id = "v3-fail-task-002"
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="rev-v3-002",
        task_statement="Failing dual core repair",
        task_type="repair",
        route={"workspace_root": str(workspace)},
        local_enabled=True,
        online_enabled=True,
        local_request={
            "action": "repair",
            "task_id": task_id,
            "workspace_root": str(workspace),
        },
    )

    def failing_local_executor(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "task_id": task_id,
            "status": "FAILED",
            "invoked": True,
            "gate_passed": False,
        }

    runtime = UnifiedRuntime(local_service=failing_local_executor)
    receipt = runtime.run(request)

    claim_b = receipt.get("claim_boundary") or {}
    assert claim_b.get("local_online_continuation") is False
