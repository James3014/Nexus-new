"""Tool Exposure Core Evidence Trust & Completion Claim Binding (#1138).

Consumes physical tool-exposure receipts produced under #982 and validates
that Core EvidenceBundle observations fail closed whenever a completion claim
requires physical tool-exposure evidence but the receipt is missing, stale,
substituted, unobserved, or merely requested.
"""

from __future__ import annotations

from typing import Any, Mapping

from nexus.contracts.tool_exposure_receipt import (
    PHYSICALLY_ENFORCED_MODES,
    ToolExposureError,
    validate_tool_exposure_receipt,
)

TOOL_EXPOSURE_VERIFIER_ID = "tool_exposure"


class ToolExposureTrustError(ValueError):
    """Raised when tool exposure evidence trust fails."""


def bind_tool_exposure_observation(
    receipt: Mapping[str, Any] | None,
    *,
    expected_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert an authoritative exposure receipt into a Core observation.

    Fail-closed:
    - If receipt is None, returns status="FAIL" with MISSING_RECEIPT.
    - If validation fails or identity drifts, returns status="FAIL".
    - If enforcement_mode is NOT in PHYSICALLY_ENFORCED_MODES, returns status="FAIL".
    - Only a verified receipt with ENFORCED_* produces status="PASS".
    """
    if receipt is None:
        return {
            "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
            "artifact_id": "tool-exposure-none",
            "artifact_hash": "sha256:" + "0" * 64,
            "status": "FAIL",
            "reason": "MISSING_TOOL_EXPOSURE_RECEIPT",
        }

    expected_kwargs = {}
    if expected_binding is not None:
        required_identity_fields = (
            "operation_id",
            "attempt_id",
            "planner_decision_hash",
            "projection_hash",
            "provider",
            "backend_id",
        )
        missing = [field for field in required_identity_fields if not expected_binding.get(field)]
        if missing:
            return {
                "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
                "artifact_id": "tool-exposure-unbound",
                "artifact_hash": "sha256:" + "0" * 64,
                "status": "FAIL",
                "reason": f"TOOL_EXPOSURE_BINDING_INCOMPLETE:{','.join(missing)}",
            }
        expected_kwargs = {
            "expected_operation_id": expected_binding.get("operation_id"),
            "expected_attempt_id": expected_binding.get("attempt_id"),
            "expected_planner_decision_hash": expected_binding.get("planner_decision_hash"),
            "expected_projection_hash": expected_binding.get("projection_hash"),
            "expected_provider": expected_binding.get("provider"),
            "expected_backend_id": expected_binding.get("backend_id"),
        }

    try:
        validated = validate_tool_exposure_receipt(receipt, **expected_kwargs)
    except ToolExposureError as exc:
        return {
            "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
            "artifact_id": f"tool-exposure-{receipt.get('operation_id', 'unknown')}-{receipt.get('attempt_id', 'unknown')}",
            "artifact_hash": "sha256:" + str(receipt.get("exposure_hash") or "0" * 64).removeprefix("sha256:"),
            "status": "FAIL",
            "reason": str(exc),
        }

    mode = validated.get("enforcement_mode")
    is_enforced = mode in PHYSICALLY_ENFORCED_MODES
    obs_status = "PASS" if is_enforced else "FAIL"
    reason = "VERIFIED_PHYSICALLY_ENFORCED" if is_enforced else f"UNENFORCED_MODE:{mode}"

    return {
        "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
        "artifact_id": f"tool-exposure-{validated['operation_id']}-{validated['attempt_id']}",
        "artifact_hash": "sha256:" + validated["exposure_hash"],
        "status": obs_status,
        "reason": reason,
        "enforcement_mode": mode,
        "operation_id": validated["operation_id"],
        "attempt_id": validated["attempt_id"],
        "provider": validated["provider"],
        "backend_id": validated["backend_id"],
        "planner_decision_hash": validated["planner_decision_hash"],
        "projection_hash": validated["projection_hash"],
        "actual_exposed_tools": validated["actual_exposed_tools"],
        "actual_exposed_tool_count": validated["actual_exposed_tool_count"],
    }


def verify_completion_claim_exposure(
    evidence_bundle: Mapping[str, Any],
    *,
    requires_physical_tool_exposure: bool,
    expected_binding: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Verify completion evidence without trusting a naked PASS assertion."""
    if not requires_physical_tool_exposure:
        return True, "EXPOSURE_EVIDENCE_NOT_REQUIRED"

    observations = evidence_bundle.get("observations") or ()
    exposure_obs = None
    for obs in observations:
        if isinstance(obs, Mapping) and obs.get("verifier_id") == TOOL_EXPOSURE_VERIFIER_ID:
            exposure_obs = obs
            break

    if exposure_obs is None:
        return False, "MISSING_PHYSICAL_TOOL_EXPOSURE_EVIDENCE"
    if exposure_obs.get("status") != "PASS":
        return False, f"UNENFORCED_TOOL_EXPOSURE:{exposure_obs.get('reason', 'UNKNOWN')}"
    if expected_binding is None:
        return False, "TOOL_EXPOSURE_BINDING_REQUIRED"

    fields = (
        "operation_id",
        "attempt_id",
        "provider",
        "backend_id",
        "planner_decision_hash",
        "projection_hash",
    )
    for field in fields:
        expected = expected_binding.get(field)
        if expected is None:
            return False, f"TOOL_EXPOSURE_BINDING_INCOMPLETE:{field}"
        if exposure_obs.get(field) != expected:
            return False, f"STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:{field}"

    expected_artifact_id = (
        f"tool-exposure-{expected_binding['operation_id']}-{expected_binding['attempt_id']}"
    )
    if exposure_obs.get("artifact_id") != expected_artifact_id:
        return False, "STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:artifact_id"

    expected_hash = expected_binding.get("exposure_hash")
    if expected_hash is not None:
        expected_hash = str(expected_hash)
        if not expected_hash.startswith("sha256:"):
            expected_hash = "sha256:" + expected_hash
        if exposure_obs.get("artifact_hash") != expected_hash:
            return False, "STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:exposure_hash"

    return True, "TOOL_EXPOSURE_VERIFIED"
