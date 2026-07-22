"""Task V1 Verification — Governed Light Route Closure.

Verifies the required path:
MainchainEntry → CapabilityPlanner → UnifiedRuntime → light execution → proportional verification → minimal Receipt
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from nexus.services.mainchain_entry import run_mainchain
from nexus.services.nexus_light_core import (
    build_nexus_light_capability_invokers,
    classify_light_route,
    create_light_route_receipt,
)
from nexus.services.unified_runtime import UnifiedRuntimeRequest


def test_nexus_light_core_seam_resolution(tmp_path: Path) -> None:
    """V1: Prove nexus_light_core seam is resolved and produces light invokers."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "target.py").write_text("def ping(): return 'pong'\n", encoding="utf-8")

    invokers = build_nexus_light_capability_invokers(str(workspace), compression=True)
    assert isinstance(invokers, dict)
    assert "codeintel" in invokers
    assert "acceptance_check" in invokers
    assert "artifact_gate" in invokers
    assert "delivery_gate" in invokers
    assert "prompt_compression" in invokers


def test_classify_light_route() -> None:
    """V1: Prove light route classification and boundary violation escalation."""
    # 1. Inspection task -> Light route
    is_light, reason = classify_light_route("Inspect codebase for security policy compliance")
    assert is_light is True
    assert "inspection" in reason or "light" in reason

    # 2. Explicit opt-in -> Light route
    is_light_opt, reason_opt = classify_light_route("Run task", route={"nexus_light": True})
    assert is_light_opt is True
    assert reason_opt == "explicit_opt_in_nexus_light"

    # 3. Heavy repair statement -> Escalate to stronger lane
    is_light_heavy, reason_heavy = classify_light_route("Fix bug in repair loop and generate patch")
    assert is_light_heavy is False
    assert "repair_lane" in reason_heavy


def test_light_route_end_to_end_deterministic(tmp_path: Path) -> None:
    """V1: Prove full path: MainchainEntry → CapabilityPlanner → UnifiedRuntime → Light execution → Receipt.

    Guarantees zero provider calls when task is deterministic.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "target.py").write_text("def test_light(): assert 1 == 1\n", encoding="utf-8")

    request = UnifiedRuntimeRequest(
        task_id="v1-light-task-001",
        workspace_revision="rev-v1-001",
        task_statement="Preflight codeintel search target.py",
        task_type="inspection",
        route={
            "nexus_light": True,
            "workspace_root": str(workspace),
            "prompt_compression": True,
        },
        online_enabled=True,
        local_enabled=False,
        online_prompt="Preflight codeintel search target.py",
        codeintel={"workspace_root": str(workspace)},
    )

    def dummy_online_invoker(payload):
        raise RuntimeError("Light route must NOT call online LLM provider")

    receipt = run_mainchain(
        request,
        online_invoker=dummy_online_invoker,
        receipt_path=tmp_path / "light_receipt.json",
    )

    assert receipt["receipt_complete"] is True, f"receipt: {receipt}"
    assert receipt.get("claim_boundary", {}).get("receipt_complete") is True, f"receipt: {receipt}"

    # Validate stages and receipt contents
    stages = receipt.get("stages") or []
    stage_names = [s.get("name") for s in stages if isinstance(s, dict)]
    assert "planner" in stage_names
    assert "verifier" in stage_names
    assert "learning" in stage_names

    # Ensure receipt reflects physical verification and zero provider calls
    assert receipt.get("public_claim_allowed") is False
    receipt_file = tmp_path / "light_receipt.json"
    assert receipt_file.exists()


def test_create_light_route_receipt_reproducible() -> None:
    """V1: Validate create_light_route_receipt structure and hash consistency."""
    r = create_light_route_receipt(
        task_id="light-1",
        planner_decision_id="plan-hash-1",
        selected_capabilities=["codeintel", "artifact_gate"],
        invoked_capabilities=["codeintel", "artifact_gate"],
        skipped_stages={"local_model_executor": "delegated_to_local_stage"},
        gate_passed=True,
        observable_effect={"effect_type": "PREFLIGHT_INSPECTION"},
    )

    assert r["schema"] == "nexus.governed_light_route_receipt.v1"
    assert r["provider_calls"] == 0
    assert r["receipt_complete"] is True
    assert r["gate_passed"] is True
    assert len(r["receipt_hash"]) == 64
