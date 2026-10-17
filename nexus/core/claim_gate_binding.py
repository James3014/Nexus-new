"""Claim-gate verifier-artifact/source-hash binding (#1757, #1869).

Single owner of the content validation shared by the receipt adapters, the executor registry
and the LocalHeal producers. Core-owned so core modules can use it without importing upper layers.
"""

from __future__ import annotations

from typing import Any

# Receipt names that are bound claim gates (verifier artifact + source hash). Non-claim adapters
# (llm_judge_panel, autoreason, ...) are not claim evidence (#1869, #2361).
BOUND_CLAIM_GATE_NAMES: frozenset[str] = frozenset({"artifact_gate"})


def _looks_like_verifier_artifact(value: Any) -> bool:
    """True only for sha256:<64 hex> or bare 64-hex — never arbitrary strings."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return False
    lower = v.lower()
    if lower.startswith("sha256:"):
        hexpart = lower[7:]
        return len(hexpart) == 64 and all(c in "0123456789abcdef" for c in hexpart)
    return len(lower) == 64 and all(c in "0123456789abcdef" for c in lower)


_PASSING_VERIFIER_STATUSES = frozenset({"pass", "passed", "verified"})


def _looks_like_source_hash(value: Any) -> bool:
    """sha256:<64 hex>, bare 64-hex, or bare 40-hex (git object id)."""
    if not isinstance(value, str):
        return False
    lower = value.strip().lower()
    if lower.startswith("sha256:"):
        lower = lower[7:]
    return (
        len(lower) in (40, 64)
        and all(c in "0123456789abcdef" for c in lower)
        and (len(lower) == 64 or not value.strip().lower().startswith("sha256:"))
    )


def _claim_gate_binding_reasons(payload: dict[str, Any]) -> list[str]:
    """Reasons the verifier-artifact/source-hash binding is unmet (#1757).

    Content-validated: a passing verifier_status or a sha256-shaped
    verifier_artifact, plus a well-formed source_hash. This is only the
    binding part of the claim gate; ClaimGateReceiptAdapter additionally
    requires _gate_verifier_ok. Empty list means the binding is satisfied.
    """
    reasons: list[str] = []
    artifact = payload.get("verifier_artifact")
    artifact_ok = type(artifact) is str and _looks_like_verifier_artifact(artifact)
    status = payload.get("verifier_status")
    if status is None:
        status_text = ""
    elif type(status) is str:
        status_text = status.strip().lower()
    else:
        status_text = "non_string"
    status_ok = status_text in _PASSING_VERIFIER_STATUSES
    if status_text and not status_ok:
        # An explicit non-passing status is never overridden by an artifact.
        reasons.append("verifier_not_passed")
    elif not artifact_ok and not status_ok:
        reasons.append("missing_verifier_artifact")
    source_hash = payload.get("source_hash")
    if not source_hash:
        reasons.append("missing_source_hash")
    elif type(source_hash) is not str or not _looks_like_source_hash(source_hash):
        reasons.append("invalid_source_hash")
    return reasons


claim_gate_binding_reasons = _claim_gate_binding_reasons
