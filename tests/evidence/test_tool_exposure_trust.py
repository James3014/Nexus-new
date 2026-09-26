from __future__ import annotations

from nexus.contracts.tool_exposure_receipt import build_tool_exposure_receipt
from nexus.evidence.tool_exposure_trust import (
    TOOL_EXPOSURE_VERIFIER_ID,
    bind_tool_exposure_observation,
    verify_completion_claim_exposure,
)


def _make_receipt(enforcement_mode: str = "ENFORCED_NATIVE_PROVIDER", **kwargs) -> dict:
    defaults = {
        "operation_id": "op-wave1",
        "attempt_id": "att-1",
        "provider": "opencode",
        "backend_id": "devspace",
        "planner_decision_hash": "1" * 64,
        "projection_hash": "2" * 64,
        "enforcement_mode": enforcement_mode,
        "candidate_tools": ["workspace.read", "workspace.list"],
        "selected_tools": ["workspace.read"],
        "actual_exposed_tools": ["workspace.read"],
    }
    defaults.update(kwargs)
    return build_tool_exposure_receipt(**defaults)


def test_enforced_label_without_physical_producer_proof_fails_closed():
    receipt = _make_receipt("ENFORCED_NATIVE_PROVIDER")
    obs = bind_tool_exposure_observation(receipt)
    assert obs["verifier_id"] == TOOL_EXPOSURE_VERIFIER_ID
    assert obs["status"] == "FAIL"
    assert obs["reason"] == "PHYSICAL_TOOL_EXPOSURE_PRODUCER_UNVERIFIED"
    assert obs["enforcement_mode"] == "ENFORCED_NATIVE_PROVIDER"
    assert obs["actual_exposed_tools"] == ["workspace.read"]

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
            "exposure_hash": receipt["exposure_hash"],
        },
    )
    assert ok is False
    assert reason == ("UNENFORCED_TOOL_EXPOSURE:PHYSICAL_TOOL_EXPOSURE_PRODUCER_UNVERIFIED")


def test_request_only_not_enforced_fails_closed():
    receipt = _make_receipt("REQUEST_ONLY_NOT_ENFORCED")
    obs = bind_tool_exposure_observation(receipt)
    assert obs["status"] == "FAIL"
    assert "UNENFORCED_MODE" in obs["reason"]

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
    )
    assert ok is False
    assert "UNENFORCED_TOOL_EXPOSURE" in reason


def test_not_observed_mode_fails_closed():
    receipt = _make_receipt("NOT_OBSERVED")
    obs = bind_tool_exposure_observation(receipt)
    assert obs["status"] == "FAIL"

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
    )
    assert ok is False
    assert "UNENFORCED_TOOL_EXPOSURE" in reason


def test_missing_receipt_fails_closed():
    obs = bind_tool_exposure_observation(None)
    assert obs["status"] == "FAIL"
    assert obs["reason"] == "MISSING_TOOL_EXPOSURE_RECEIPT"

    evidence_bundle = {"observations": [obs]}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
    )
    assert ok is False
    assert "UNENFORCED_TOOL_EXPOSURE" in reason

    # Totally missing from bundle
    ok_empty, reason_empty = verify_completion_claim_exposure(
        {"observations": []},
        requires_physical_tool_exposure=True,
    )
    assert ok_empty is False
    assert reason_empty == "MISSING_PHYSICAL_TOOL_EXPOSURE_EVIDENCE"


def test_stale_or_substituted_attempt_receipt_fails_closed():
    # Exercise the completion-layer identity check independently of producer trust.
    receipt = _make_receipt("ENFORCED_MANAGED_BRIDGE", attempt_id="att-1")
    obs = {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": "tool-exposure-op-wave1-att-1",
        "artifact_hash": "sha256:" + receipt["exposure_hash"],
        "status": "PASS",
        "reason": "HYPOTHETICAL_TRUSTED_PHYSICAL_PRODUCER",
        "operation_id": "op-wave1",
        "attempt_id": "att-1",
        "provider": "opencode",
        "backend_id": "devspace",
        "planner_decision_hash": "1" * 64,
        "projection_hash": "2" * 64,
    }
    evidence_bundle = {"observations": [obs]}

    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-2",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
        },
    )
    assert ok is False
    assert reason == "STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:attempt_id"


def test_tampered_receipt_fails_observation():
    receipt = _make_receipt("ENFORCED_MANAGED_BRIDGE")
    # Tamper with actual_exposed_tools
    receipt["actual_exposed_tools"] = ["workspace.read", "workspace.mutate"]
    obs = bind_tool_exposure_observation(receipt)
    assert obs["status"] == "FAIL"


def test_forged_pass_observation_without_bound_identity_fails_closed():
    forged = {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": "tool-exposure-op-wave1-att-1",
        "artifact_hash": "sha256:" + "f" * 64,
        "status": "PASS",
    }
    ok, reason = verify_completion_claim_exposure(
        {"observations": [forged]},
        requires_physical_tool_exposure=True,
        expected_binding={
            "operation_id": "op-wave1",
            "attempt_id": "att-1",
            "provider": "opencode",
            "backend_id": "devspace",
            "planner_decision_hash": "1" * 64,
            "projection_hash": "2" * 64,
        },
    )
    assert ok is False
    assert "STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT" in reason


def test_unrequired_exposure_passes_without_evidence():
    evidence_bundle = {"observations": []}
    ok, reason = verify_completion_claim_exposure(
        evidence_bundle,
        requires_physical_tool_exposure=False,
    )
    assert ok is True
    assert reason == "EXPOSURE_EVIDENCE_NOT_REQUIRED"
