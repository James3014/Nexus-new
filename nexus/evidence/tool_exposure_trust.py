"""Tool Exposure Core Evidence Trust & Completion Claim Binding (#1138, #1144).

Consumes physical tool-exposure receipts produced under #982 and validates
that Core EvidenceBundle observations fail closed whenever a completion claim
requires physical tool-exposure evidence but the receipt is missing, stale,
substituted, unobserved, or merely requested.

Binds approved remote MCP tool authority identity through physical invocation
and Core completion (#1144).
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
    - An ENFORCED_* label alone is not physical producer proof. Until #982
      supplies a canonical provider/runtime provenance path, it also fails closed.
    - If remote tool identity is expected or required, validates stable tool authority
      identity and runtime generation evidence fail-closed (#1144).
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

        requires_remote = bool(
            expected_binding.get("requires_remote_tool_identity")
            or expected_binding.get("expected_remote_tool_identities")
        )
        expected_kwargs = {
            "expected_operation_id": expected_binding.get("operation_id"),
            "expected_attempt_id": expected_binding.get("attempt_id"),
            "expected_planner_decision_hash": expected_binding.get("planner_decision_hash"),
            "expected_projection_hash": expected_binding.get("projection_hash"),
            "expected_provider": expected_binding.get("provider"),
            "expected_backend_id": expected_binding.get("backend_id"),
            "expected_remote_tool_identities": expected_binding.get(
                "expected_remote_tool_identities"
            ),
            "expected_runtime_tool_generations": expected_binding.get(
                "expected_runtime_tool_generations"
            ),
            "require_remote_tool_identity": requires_remote,
        }

    try:
        validated = validate_tool_exposure_receipt(receipt, **expected_kwargs)
    except ToolExposureError as exc:
        return {
            "verifier_id": TOOL_EXPOSURE_VERIFIER_ID,
            "artifact_id": f"tool-exposure-{receipt.get('operation_id', 'unknown')}-{receipt.get('attempt_id', 'unknown')}",
            "artifact_hash": "sha256:"
            + str(receipt.get("exposure_hash") or "0" * 64).removeprefix("sha256:"),
            "status": "FAIL",
            "reason": str(exc),
        }

    mode = validated.get("enforcement_mode")
    is_enforced = mode in PHYSICALLY_ENFORCED_MODES
    obs_status = "FAIL"
    reason = (
        "PHYSICAL_TOOL_EXPOSURE_PRODUCER_UNVERIFIED" if is_enforced else f"UNENFORCED_MODE:{mode}"
    )

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
        "remote_tool_identities": validated.get("remote_tool_identities", []),
        "runtime_tool_generations": validated.get("runtime_tool_generations", []),
        "stable_tool_ids": [
            ident["stable_tool_id"]
            for ident in validated.get("remote_tool_identities", [])
            if isinstance(ident, Mapping) and "stable_tool_id" in ident
        ],
    }


def verify_completion_claim_exposure(
    evidence_bundle: Mapping[str, Any],
    *,
    requires_physical_tool_exposure: bool,
    expected_binding: Mapping[str, Any] | None = None,
) -> tuple[bool, str]:
    """Verify completion evidence without trusting a naked PASS assertion.

    Binds approved remote MCP tool authority identity through physical invocation
    and Core completion (#1144).
    """
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

    # Enforce remote tool identity binding when required (#1144)
    requires_remote = bool(
        expected_binding.get("requires_remote_tool_identity")
        or expected_binding.get("expected_remote_tool_identities")
    )
    if requires_remote:
        remote_identities = exposure_obs.get("remote_tool_identities") or []
        if not remote_identities:
            return False, "MISSING_REMOTE_TOOL_IDENTITY_EVIDENCE"

        expected_remotes = expected_binding.get("expected_remote_tool_identities")
        if expected_remotes:
            for exp in expected_remotes:
                exp_origin = exp.get("server_origin")
                exp_name = exp.get("tool_name")
                exp_stable_id = exp.get("stable_tool_id")

                match = next(
                    (
                        r
                        for r in remote_identities
                        if r.get("server_origin") == exp_origin and r.get("tool_name") == exp_name
                    ),
                    None,
                )
                if match is None:
                    return (
                        False,
                        f"STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:remote_tool_origin_mismatch:{exp_origin}/{exp_name}",
                    )
                if exp_stable_id and match.get("stable_tool_id") != exp_stable_id:
                    return (
                        False,
                        f"STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:remote_tool_identity_drift:{exp_name}",
                    )

        expected_gens = expected_binding.get("expected_runtime_tool_generations")
        if expected_gens:
            runtime_gens = exposure_obs.get("runtime_tool_generations") or []
            for exp_g in expected_gens:
                exp_orig = exp_g.get("server_origin")
                exp_inst = exp_g.get("server_instance_id")
                exp_cat = exp_g.get("catalog_generation")

                match_g = next(
                    (g for g in runtime_gens if g.get("server_origin") == exp_orig),
                    None,
                )
                if match_g is None:
                    return (
                        False,
                        f"STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:runtime_generation_missing:{exp_orig}",
                    )
                if exp_inst and match_g.get("server_instance_id") != exp_inst:
                    return (
                        False,
                        f"STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:runtime_generation_instance_drift:{exp_orig}",
                    )
                if exp_cat is not None and match_g.get("catalog_generation") != exp_cat:
                    return (
                        False,
                        f"STALE_OR_SUBSTITUTED_TOOL_EXPOSURE_RECEIPT:runtime_generation_drift:{exp_orig}",
                    )

    return True, "TOOL_EXPOSURE_VERIFIED"
