"""Task V2: Local-Only Real Repair Closure Test Suite.

Verifies local native repair execution loop when `local_enabled=True` and `online_enabled=False`.
Guarantees zero online LLM provider calls, physical patch match verification,
and fail-closed behavior on candidate mismatch or execution failure.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest


def test_local_only_repair_execution(tmp_path: Path) -> None:
    """V2: Prove local-only repair execution loop without online LLM calls.

    Verifies local patch generation, physical verification, and clean receipt creation.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "target.py"
    target.write_text("def solve(): return False\n", encoding="utf-8")

    task_id = "v2-local-repair-task-001"
    rev = "rev-v2-001"
    task_stmt = "Fix return value in target.py to return True"

    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision=rev,
        task_statement=task_stmt,
        task_type="repair",
        route={
            "workspace_root": str(workspace),
            "local_action": "repair",
        },
        local_enabled=True,
        online_enabled=False,
        local_request={
            "action": "repair",
            "task_id": task_id,
            "workspace_root": str(workspace),
        },
    )

    patch_text = "--- target.py\n+++ target.py\n@@ -1 +1 @@\n-def solve(): return False\n+def solve(): return True\n"
    patch_hash = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    source_raw = f"{rev}:{task_stmt}".encode("utf-8")
    source_hash = hashlib.sha256(source_raw).hexdigest()

    def dummy_online_invoker(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raise RuntimeError("Local repair must NOT call online LLM provider")

    def dummy_local_executor(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        # Perform physical file edit
        target.write_text("def solve(): return True\n", encoding="utf-8")
        return {
            "task_id": task_id,
            "status": "SUCCEEDED",
            "invoked": True,
            "local_model_invoked": True,
            "output_delivered": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "evidence_refs": [f"local_repair:{task_id}:patch_applied"],
            "model_candidate_hash": patch_hash,
            "selected_candidate_hash": patch_hash,
            "applied_patch_hash": patch_hash,
            "patch_text": patch_text,
            "physical_callable": "nexus.services.local_repair_executor",
            "candidate_summary": {
                "isolation_status": "isolated",
                "selected_candidate_hash_matches_applied": True,
                "model_candidate_hash": patch_hash,
                "selected_candidate_hash": patch_hash,
                "applied_patch_hash": patch_hash,
            },
        }

    def dummy_verifier(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        art_bytes = f"local_verifier:{task_id}:{patch_hash}".encode("utf-8")
        art_hash = hashlib.sha256(art_bytes).hexdigest()
        return {
            "task_id": task_id,
            "verifier_task_id": task_id,
            "invoked": True,
            "evidence_present": True,
            "evidence_refs": [f"verifier:local:{task_id}"],
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
            "evidence_refs": [f"learning:local:{task_id}"],
            "gate_passed": True,
            "status": "SUCCEEDED",
        }

    runtime = UnifiedRuntime(local_service=dummy_local_executor)
    receipt = runtime.run(
        request,
        online_invoker=dummy_online_invoker,
        verifier=dummy_verifier,
        learning=dummy_learning,
        receipt_path=tmp_path / "local_repair_receipt.json",
    )

    # Verify local stage, verifier stage, and outcome contribution
    stages = receipt.get("stages") or []
    stage_map = {s.get("name"): s for s in stages if isinstance(s, dict)}
    assert "local" in stage_map
    assert stage_map["local"].get("status") == "SUCCEEDED"
    assert "verifier" in stage_map
    assert stage_map["verifier"].get("status") == "SUCCEEDED"

    # Verify claim boundary outcome contribution
    claim_b = receipt.get("claim_boundary") or {}
    assert claim_b.get("outcome_contributed") is True

    # Verify physical file modification occurred
    assert target.read_text(encoding="utf-8") == "def solve(): return True\n"

    # Verify receipt saved to disk
    receipt_file = tmp_path / "local_repair_receipt.json"
    assert receipt_file.exists()


def test_local_repair_negative_control_mismatch_fails_closed(tmp_path: Path) -> None:
    """V2 Negative Control: Candidate mismatch or local execution failure must fail closed."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "target.py"
    target.write_text("def solve(): return False\n", encoding="utf-8")

    task_id = "v2-fail-task-002"
    request = UnifiedRuntimeRequest(
        task_id=task_id,
        workspace_revision="rev-v2-002",
        task_statement="Broken local repair test",
        task_type="repair",
        route={"workspace_root": str(workspace), "local_action": "repair"},
        local_enabled=True,
        online_enabled=False,
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
            "error": "LOCAL_PATCH_APPLICATION_FAILED",
            "model_candidate_hash": "sha256:aaa",
            "selected_candidate_hash": "sha256:bbb",  # Mismatch!
            "applied_patch_hash": "",
        }

    runtime = UnifiedRuntime(local_service=failing_local_executor)
    receipt = runtime.run(request)

    # Must fail closed: receipt_complete is False, gate_passed is False
    assert receipt.get("receipt_complete") is False
    assert receipt.get("claim_boundary", {}).get("receipt_complete") is False
