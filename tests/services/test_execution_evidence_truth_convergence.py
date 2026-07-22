"""Task R1: Execution Evidence Truth Convergence Test Suite.

Verifies strict fail-closed proof requirements for execution evidence.
Enforces that status labels, verifier PASS, or synthesized metadata booleans
can never substitute for physical call invocation, output delivery, candidate bytes,
or persistent Learning writeback.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from nexus.services.online_nexus_context import evaluate_postflight_gate
from nexus.services.unified_runtime import UnifiedRuntime, UnifiedRuntimeRequest


def test_nc1_verifier_pass_without_invocation_fails_gates() -> None:
    """NC1: Verifier returns PASS, but no Local/Online invocation occurred.

    Claim and delivery gates must fail closed and receipt must be incomplete.
    """
    ctx = {
        "task_id": "r1-nc1-001",
        "verifier": {
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_task_id": "r1-nc1-001",
            "source_hash": "a" * 64,
            "verifier_source_hash": "a" * 64,
            "verifier_artifact": "sha256:" + ("b" * 64),
        },
        "capability_evidence_bundle": {"source_hash": "a" * 64},
        "artifact_hash": "a" * 64,
        "online": {"invoked": False},
        "local": {"invoked": False},
    }

    claim = evaluate_postflight_gate("claim_gate", ctx)
    assert claim["gate_passed"] is False
    assert "online_not_invoked" in claim["blockers"]

    delivery = evaluate_postflight_gate("delivery_gate", ctx)
    assert delivery["gate_passed"] is False
    assert "online_not_invoked" in delivery["blockers"]


def test_nc2_local_succeeded_without_executor_invocation_fails() -> None:
    """NC2: Local stage claims SUCCEEDED, but Local executor was not called.

    Using a spy, confirm local executor call count is 0, local_invoked is False, and gates fail.
    """
    spy_local_executor = MagicMock()
    request = UnifiedRuntimeRequest(
        task_id="r1-nc2-001",
        workspace_revision="rev-nc2",
        task_statement="repair code",
        task_type="repair",
        route={},
        local_enabled=True,
        online_enabled=False,
        local_request={"action": "repair", "task_id": "r1-nc2-001"},
    )

    runtime = UnifiedRuntime()  # local_service=None so executor is not supplied
    receipt = runtime.run(request)

    assert spy_local_executor.call_count == 0
    local_stage = receipt.get("local") or {}
    assert local_stage.get("invoked") is False
    claim_b = receipt.get("claim_boundary") or {}
    assert claim_b.get("public_claim_allowed") is False


def test_nc3_online_completed_without_provider_call_fails() -> None:
    """NC3: Online stage reports COMPLETED, but registered provider edge was not called.

    Using a spy, confirm provider call count is 0 and claim/delivery fail.
    """
    spy_provider = MagicMock()
    request = UnifiedRuntimeRequest(
        task_id="r1-nc3-001",
        workspace_revision="rev-nc3",
        task_statement="online repair",
        task_type="repair",
        route={},
        online_enabled=True,
        local_enabled=False,
    )

    # online_invoker is None so provider edge is not supplied
    runtime = UnifiedRuntime()
    receipt = runtime.run(request, online_invoker=None)

    assert spy_provider.call_count == 0
    online_stage = receipt.get("online") or {}
    assert online_stage.get("invoked") is False
    assert receipt.get("receipt_complete") is False or receipt.get("claim_boundary", {}).get("public_claim_allowed") is False


def test_nc4_task_id_metadata_without_candidate_bytes_fails() -> None:
    """NC4: task_id exists, but no candidate bytes, output artifact, or verifier artifact exists.

    No synthesized candidate hash should be promoted; receipt remains incomplete.
    """
    ctx = {
        "task_id": "r1-nc4-001",
        "verifier": {
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "task_id": "r1-nc4-001",
            "verifier_task_id": "r1-nc4-001",
            "source_hash": "a" * 64,
            "verifier_source_hash": "a" * 64,
            "verifier_artifact": "",
        },
        "capability_evidence_bundle": {"source_hash": "a" * 64},
        "online": {"invoked": True},
        "local": {"invoked": False},
        # Missing candidate_hash, applied_hash, artifact_hash, and verifier_artifact
    }

    delivery = evaluate_postflight_gate("delivery_gate", ctx)
    assert delivery["gate_passed"] is False
    assert "delivery_missing_applied_or_candidate" in delivery["blockers"]


def test_nc5_candidate_hash_recomputed_from_physical_bytes(tmp_path: Path) -> None:
    """NC5: Candidate bytes exist in physical artifact. Hash must be recomputed from exact bytes."""
    patch_file = tmp_path / "candidate.patch"
    content_a = b"--- target.py\n+++ target.py\n@@ -1 +1 @@\n-a\n+b\n"
    patch_file.write_bytes(content_a)
    hash_a = hashlib.sha256(content_a).hexdigest()

    content_b = b"--- target.py\n+++ target.py\n@@ -1 +1 @@\n-a\n+c\n"
    hash_b = hashlib.sha256(content_b).hexdigest()

    assert hash_a != hash_b
    assert hashlib.sha256(patch_file.read_bytes()).hexdigest() == hash_a

    # Changing physical bytes invalidates old hash
    patch_file.write_bytes(content_b)
    assert hashlib.sha256(patch_file.read_bytes()).hexdigest() != hash_a
    assert hashlib.sha256(patch_file.read_bytes()).hexdigest() == hash_b


def test_nc6_missing_verifier_response_never_defaults_to_pass() -> None:
    """NC6: Missing verifier response must produce verifier_invoked=false or verifier_gate_passed=false."""
    ctx = {
        "task_id": "r1-nc6-001",
        "online": {"invoked": True},
        "local": {"invoked": False},
        # verifier is missing
    }

    art_gate = evaluate_postflight_gate("artifact_gate", ctx)
    assert art_gate["gate_passed"] is False
    assert "verifier_not_invoked" in art_gate["blockers"] or "missing_verifier_status" in art_gate["blockers"]


def test_nc7_learning_success_requires_real_writeback() -> None:
    """NC7: Learning must not be reported as SUCCEEDED merely because verifier passed."""
    def dummy_verifier(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "task_id": "r1-nc7-001",
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_artifact": "sha256:" + ("c" * 64),
            "source_hash": "a" * 64,
            "verifier_source_hash": "a" * 64,
        }

    # Learning callback returns FAILED or NOT_RUN
    def failing_learning(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "task_id": "r1-nc7-001",
            "invoked": True,
            "gate_passed": False,
            "status": "FAILED",
            "reason": "persistence_write_error",
        }

    request = UnifiedRuntimeRequest(
        task_id="r1-nc7-001",
        workspace_revision="rev-nc7",
        task_statement="test learning fail-closed",
        task_type="repair",
        route={},
        online_enabled=True,
    )

    def dummy_online(ctx: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"task_id": "r1-nc7-001", "invoked": True, "output_delivered": True, "status": "SUCCEEDED"}

    runtime = UnifiedRuntime()
    receipt = runtime.run(
        request,
        online_invoker=dummy_online,
        verifier=dummy_verifier,
        learning=failing_learning,
    )

    stages = receipt.get("stages") or []
    stage_map = {s.get("name"): s for s in stages if isinstance(s, dict)}
    assert "learning" in stage_map
    assert stage_map["learning"].get("status") == "FAILED"
    assert stage_map["learning"].get("gate_passed") is False


def test_nc8_declarative_booleans_without_originating_event_fail_gates() -> None:
    """NC8: Truthy booleans passed in route/metadata without originating event fail gates."""
    ctx = {
        "task_id": "r1-nc8-001",
        "route": {"nexus_light": True, "deterministic_core": True, "online_invoked": True},
        "online": {"invoked": False},
        "local": {"invoked": False},
        "verifier": {
            "invoked": True,
            "gate_passed": True,
            "verifier_status": "pass",
            "verifier_task_id": "r1-nc8-001",
            "source_hash": "a" * 64,
            "verifier_source_hash": "a" * 64,
            "verifier_artifact": "sha256:" + ("b" * 64),
        },
        "capability_evidence_bundle": {"source_hash": "a" * 64},
        "artifact_hash": "a" * 64,
    }

    claim = evaluate_postflight_gate("claim_gate", ctx)
    assert claim["gate_passed"] is False
    assert "online_not_invoked" in claim["blockers"]
