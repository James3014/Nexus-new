from __future__ import annotations

from typing import Any, Mapping


APPROVED_PROMOTION_SANDBOX_MODES = {"macos_sandbox", "linux_cgroup"}


def build_mock_sandbox_attestation(
    *,
    artifact_hash: str,
    network_disabled: bool = True,
    workspace_isolated: bool = True,
    tmp_isolated: bool = True,
    teardown_status: str = "PASS",
) -> dict[str, Any]:
    return {
        "issuer": "nexus.runner",
        "sandbox_mode": "mocked_non_promotion",
        "status": "PASS" if teardown_status == "PASS" else "FAIL",
        "network_disabled": network_disabled,
        "workspace_isolated": workspace_isolated,
        "tmp_isolated": tmp_isolated,
        "env_allowlist_hash": "mock-env-allowlist",
        "resource_limits": {"cpu": "mock", "memory_mb": 512, "timeout_sec": 3},
        "teardown_status": teardown_status,
        "artifact_hash": artifact_hash,
        "signature": "mock-non-promotion",
    }


def validate_sandbox_attestation(attestation: Mapping[str, Any], *, allow_mock_for_promotion: bool = False) -> dict[str, Any]:
    reasons: list[str] = []
    if attestation.get("issuer") != "nexus.runner":
        reasons.append("invalid_sandbox_issuer")
    mode = str(attestation.get("sandbox_mode") or "")
    if mode == "mocked_non_promotion" and not allow_mock_for_promotion:
        reasons.append("mocked_sandbox_non_promotion")
    elif mode not in APPROVED_PROMOTION_SANDBOX_MODES and mode != "mocked_non_promotion":
        reasons.append("unapproved_sandbox_mode")
    if attestation.get("status") != "PASS":
        reasons.append("sandbox_status_not_pass")
    if attestation.get("network_disabled") is not True:
        reasons.append("network_not_disabled")
    if attestation.get("workspace_isolated") is not True:
        reasons.append("workspace_not_isolated")
    if attestation.get("tmp_isolated") is not True:
        reasons.append("tmp_not_isolated")
    if attestation.get("teardown_status") != "PASS":
        reasons.append("teardown_not_pass")
    if not attestation.get("signature"):
        reasons.append("missing_sandbox_signature")
    status = "PASS" if not reasons else "BLOCKED"
    return {"status": status, "reasons": sorted(set(reasons)), "sandbox_mode": mode}
