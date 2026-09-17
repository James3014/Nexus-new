from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Protocol

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SESSION_RE = re.compile(r"^cms_[0-9a-f]{32}$")
_COMMIT_RE = re.compile(r"^git-commit:[0-9a-f]{40}$")
_TREE_RE = re.compile(r"^git-tree:[0-9a-f]{40}$")
CORE_RESPONSE_SCHEMA = "nexus.core.generic-verification-response.v1-experimental"
PREPARATION_SCHEMA = "nexus.ambient-core-preparation.v1"
VERIFICATION_PROJECTION_SCHEMA = "nexus.ambient-core-verification-projection.v1"


class AmbientCoreControlPort(Protocol):
    """Host transport boundary; it owns no route, lane, worker or completion truth."""

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]: ...

    def revalidate_mutation_binding(self, preparation: Mapping[str, Any], **kwargs: Any) -> None: ...

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]: ...


def ambient_core_required(request: Mapping[str, Any]) -> bool:
    value = request.get("core_envelope_required", False)
    if type(value) is not bool:
        raise ValueError("core_envelope_required must be boolean")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\0" in value:
        raise RuntimeError(f"AMBIENT_CORE_INVALID:{field}")
    return value


def normalize_preparation(value: Mapping[str, Any], *, attempt_id: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise RuntimeError("AMBIENT_CORE_PREPARATION_INVALID")
    normalized = {
        "schema": PREPARATION_SCHEMA,
        "session_id": _required_text(value.get("session_id"), "session_id"),
        "binding_id": _required_text(value.get("binding_id"), "binding_id"),
        "binding_hash": _required_text(value.get("binding_hash"), "binding_hash"),
        "operation_id": _required_text(value.get("operation_id"), "operation_id"),
        "attempt_id": _required_text(value.get("attempt_id"), "attempt_id"),
        "acceptance_contract_hash": _required_text(
            value.get("acceptance_contract_hash"), "acceptance_contract_hash"
        ),
        "source_revision": _required_text(value.get("source_revision"), "source_revision"),
        "source_tree": _required_text(value.get("source_tree"), "source_tree"),
    }
    if not _SESSION_RE.fullmatch(normalized["session_id"]):
        raise RuntimeError("AMBIENT_CORE_INVALID:session_id")
    for field in ("binding_hash", "acceptance_contract_hash"):
        if not _HASH_RE.fullmatch(normalized[field]):
            raise RuntimeError(f"AMBIENT_CORE_INVALID:{field}")
    if not _COMMIT_RE.fullmatch(normalized["source_revision"]):
        raise RuntimeError("AMBIENT_CORE_INVALID:source_revision")
    if not _TREE_RE.fullmatch(normalized["source_tree"]):
        raise RuntimeError("AMBIENT_CORE_INVALID:source_tree")
    if normalized["attempt_id"] != attempt_id:
        raise RuntimeError("AMBIENT_CORE_ATTEMPT_MISMATCH")
    return normalized


def normalize_verification_projection(
    value: Mapping[str, Any],
    *,
    preparation: Mapping[str, Any],
    candidate_state_hash: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RuntimeError("AMBIENT_CORE_VERIFICATION_INVALID")
    if value.get("session_id") != preparation.get("session_id"):
        raise RuntimeError("AMBIENT_CORE_SESSION_MISMATCH")
    if value.get("binding_hash") != preparation.get("binding_hash"):
        raise RuntimeError("AMBIENT_CORE_BINDING_MISMATCH")
    if value.get("candidate_state_hash") != candidate_state_hash:
        raise RuntimeError("AMBIENT_CORE_CANDIDATE_STATE_MISMATCH")
    response = value.get("core_response")
    if not isinstance(response, Mapping) or response.get("schema") != CORE_RESPONSE_SCHEMA:
        raise RuntimeError("AMBIENT_CORE_RESPONSE_SCHEMA_MISMATCH")
    verification = response.get("verification")
    if not isinstance(verification, Mapping) or verification.get("status") != "VERIFIED":
        raise RuntimeError("AMBIENT_CORE_FAILED_VERIFICATION")
    hashes = response.get("hashes")
    if not isinstance(hashes, Mapping):
        raise RuntimeError("AMBIENT_CORE_HASHES_MISSING")
    required_hashes = (
        "acceptance_contract_hash",
        "change_set_hash",
        "verification_plan_hash",
        "evidence_bundle_hash",
        "change_manifest_hash",
    )
    normalized_hashes: dict[str, str] = {}
    for field in required_hashes:
        item = _required_text(hashes.get(field), field)
        if not _HASH_RE.fullmatch(item):
            raise RuntimeError(f"AMBIENT_CORE_INVALID:{field}")
        normalized_hashes[field] = item
    if normalized_hashes["acceptance_contract_hash"] != preparation.get(
        "acceptance_contract_hash"
    ):
        raise RuntimeError("AMBIENT_CORE_CONTRACT_HASH_MISMATCH")
    projection = {
        "schema": VERIFICATION_PROJECTION_SCHEMA,
        "session_id": preparation["session_id"],
        "binding_hash": preparation["binding_hash"],
        "candidate_state_hash": candidate_state_hash,
        "core_response": {
            "protocol_version": response.get("protocol_version"),
            "schema": response["schema"],
            "verification": dict(verification),
            "hashes": normalized_hashes,
            "certification": response.get("certification"),
        },
    }
    return projection


def projection_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()
