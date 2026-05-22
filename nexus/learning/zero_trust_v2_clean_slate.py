from __future__ import annotations

from typing import Any


def build_baseline_sandwich(
    *,
    baseline_before_hash: str,
    skill_arm_hash: str,
    baseline_after_hash: str,
    teardown_status: str = "PASS",
) -> dict[str, Any]:
    if baseline_before_hash == baseline_after_hash:
        delta_status = "CLEAN"
    elif not baseline_before_hash or not baseline_after_hash:
        delta_status = "INCONCLUSIVE"
    else:
        delta_status = "POLLUTED"
    return {
        "baseline_sandwich": {
            "enabled": True,
            "baseline_before_hash": baseline_before_hash,
            "skill_arm_hash": skill_arm_hash,
            "baseline_after_hash": baseline_after_hash,
            "baseline_delta_status": delta_status,
            "pollution_detector_provenance": "runtime_observer",
        },
        "cleanup_attestation": {
            "required": True,
            "teardown_status": teardown_status,
            "runner_quarantine_status": "NONE" if teardown_status == "PASS" else "QUARANTINED",
            "cleanup_observer": "nexus.runner",
            "artifact_hash": skill_arm_hash,
            "signature": "mock-cleanup",
        },
    }


def validate_clean_slate_contract(contract: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    sandwich = contract.get("baseline_sandwich") if isinstance(contract.get("baseline_sandwich"), dict) else {}
    cleanup = contract.get("cleanup_attestation") if isinstance(contract.get("cleanup_attestation"), dict) else {}
    if sandwich.get("baseline_delta_status") != "CLEAN":
        reasons.append("baseline_not_clean")
    if sandwich.get("pollution_detector_provenance") != "runtime_observer":
        reasons.append("invalid_pollution_detector")
    if cleanup.get("teardown_status") != "PASS":
        reasons.append("cleanup_not_pass")
    status = "PASS" if not reasons else "BLOCKED"
    return {
        "status": status,
        "reasons": sorted(set(reasons)),
        "runner_quarantine_status": cleanup.get("runner_quarantine_status") or "UNKNOWN",
    }
