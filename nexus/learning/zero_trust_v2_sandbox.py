from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping

from nexus.learning.zero_trust_v2_receipts import canonical_json_hash


APPROVED_PROMOTION_SANDBOX_MODES = {"macos_sandbox", "linux_cgroup"}


def sandbox_attestation_signature(
    *, attestation_body: Mapping[str, Any], signing_secret: str
) -> str:
    """HMAC-SHA256, keyed by the runner's secret, over the canonical hash of the attestation
    body (every field but ``signature``); the runner signs with it and a validator that knows
    the secret checks it (#3229)."""
    digest = canonical_json_hash(dict(attestation_body))
    return hmac.new(
        signing_secret.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256
    ).hexdigest()


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


def validate_sandbox_attestation(
    attestation: Mapping[str, Any],
    *,
    allow_mock_for_promotion: bool = False,
    signing_secret: str | None = None,
) -> dict[str, Any]:
    """Field checks on a runner attestation; with ``signing_secret`` the signature is
    verified too (a mock attestation carries none), so an attestation read back from another
    process cannot pass on the presence of the field alone (#3229)."""
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
    elif signing_secret is not None and mode != "mocked_non_promotion":
        body = {key: value for key, value in attestation.items() if key != "signature"}
        expected = sandbox_attestation_signature(
            attestation_body=body, signing_secret=signing_secret
        )
        if not hmac.compare_digest(str(attestation.get("signature")), expected):
            reasons.append("invalid_sandbox_signature")
    status = "PASS" if not reasons else "BLOCKED"
    return {"status": status, "reasons": sorted(set(reasons)), "sandbox_mode": mode}
