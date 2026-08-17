"""Strict, provider-neutral ChangeSet certification wire contract."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

CHANGESET_CERTIFICATION_SCHEMA = "nexus.changeset_certification.v1"
CHANGESET_CERTIFICATION_VERSION = 1
CLAIM_CEILING = "LOCAL_CHANGESET_CERTIFICATION_V1_CONTRACT_CANDIDATE_ONLY"
_STATUSES = frozenset({"CERTIFIED", "REJECTED", "BLOCKED"})
_VERIFIER_STATUSES = frozenset({"PASS", "FAIL"})
_HASH_LEN = 71
_REASONS = frozenset({
    "identity_missing",
    "identity_malformed",
    "evidence_missing",
    "evidence_malformed",
    "scope_missing",
    "scope_malformed",
    "candidate_malformed",
    "verifier_manifest_missing",
    "verifier_manifest_malformed",
    "verifier_missing",
    "verifier_failed",
    "verifier_artifact_missing",
    "verifier_artifact_malformed",
    "hash_mismatch",
    "manifest_hash_mismatch",
    "payload_hash_mismatch",
    "cross_binding_mismatch",
    "status_invalid",
    "reason_invalid",
    "schema_invalid",
    "unknown_field",
})


class CertificationStatus(str, Enum):
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ChangeSetIdentity:
    change_set_id: str
    source_revision: str
    target_revision: str
    diff_hash: str


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: str
    content_hash: str
    source: str


@dataclass(frozen=True)
class ChangeSetCertification:
    change_set: ChangeSetIdentity
    evidence: tuple[EvidenceRef, ...] = ()
    status: CertificationStatus = CertificationStatus.BLOCKED
    reason_codes: tuple[str, ...] = ()
    envelope: Mapping[str, Any] | None = None
    schema: str = CHANGESET_CERTIFICATION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return _copy(self.envelope) if self.envelope is not None else _legacy_wire(self)

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    def canonical_hash(self) -> str:
        return canonical_hash(self.to_dict())


def canonical_json(value: Any) -> str:
    """Canonical finite JSON; known set-like lists are semantically unordered."""
    return json.dumps(
        _normalize(value, ()),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


def certify_changeset(payload: Mapping[str, Any]) -> ChangeSetCertification:
    if not isinstance(payload, Mapping):
        return _blocked("identity_missing")
    if _is_legacy(payload):
        return _certify_legacy(payload)
    errors = _validate_envelope(payload)
    if errors:
        return _result(
            payload,
            CertificationStatus.BLOCKED
            if errors[0]
            in {
                "identity_missing",
                "evidence_missing",
                "scope_missing",
                "verifier_manifest_missing",
                "verifier_missing",
                "verifier_artifact_missing",
            }
            else CertificationStatus.REJECTED,
            errors,
        )
    manifest = payload["verifier_manifest"]
    if any(v["status"] == "FAIL" for v in manifest["verifiers"]):
        return _result(payload, CertificationStatus.REJECTED, ("verifier_failed",))
    if payload["disposition"] != "CERTIFIED":
        return _result(payload, CertificationStatus.REJECTED, ("status_invalid",))
    if payload["canonical_payload_hash"] != canonical_hash(_payload_hash_input(payload)):
        return _result(payload, CertificationStatus.REJECTED, ("payload_hash_mismatch",))
    if manifest["manifest_hash"] != canonical_hash(_manifest_hash_input(manifest)):
        return _result(payload, CertificationStatus.REJECTED, ("manifest_hash_mismatch",))
    return _result(payload, CertificationStatus.CERTIFIED, ())


def build_changeset_certification(
    *,
    change_set: Mapping[str, Any],
    evidence: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
) -> dict[str, Any]:
    return _certify_legacy({"change_set": change_set, "evidence": evidence}).to_dict()


def validate_changeset_certification(
    certification: ChangeSetCertification | Mapping[str, Any],
) -> tuple[str, ...]:
    payload = (
        certification.to_dict()
        if isinstance(certification, ChangeSetCertification)
        else certification
    )
    if not isinstance(payload, Mapping):
        return ("identity_malformed",)
    if _is_legacy(payload):
        return (
            ()
            if payload.get("status") == "CERTIFIED" and payload.get("evidence")
            else ("evidence_missing",)
        )
    errors = _validate_envelope(payload)
    if errors:
        return errors
    if payload["disposition"] == "CERTIFIED":
        if any(v["status"] == "FAIL" for v in payload["verifier_manifest"]["verifiers"]):
            return ("verifier_failed",)
        if payload["canonical_payload_hash"] != canonical_hash(_payload_hash_input(payload)):
            return ("payload_hash_mismatch",)
        if payload["verifier_manifest"]["manifest_hash"] != canonical_hash(
            _manifest_hash_input(payload["verifier_manifest"])
        ):
            return ("manifest_hash_mismatch",)
    return ()


def _validate_envelope(payload: Mapping[str, Any]) -> tuple[str, ...]:
    allowed = {
        "schema",
        "version",
        "task",
        "repository",
        "base",
        "diff",
        "allowed_scope",
        "candidate",
        "verifier_manifest",
        "disposition",
        "reasons",
        "claim_ceiling",
        "canonical_payload_hash",
    }
    if set(payload) - allowed:
        return ("unknown_field",)
    if payload.get("schema") != CHANGESET_CERTIFICATION_SCHEMA or payload.get("version") != 1:
        return ("schema_invalid",)
    task, repo, base, diff, scope = (
        payload.get(k) for k in ("task", "repository", "base", "diff", "allowed_scope")
    )
    if task is None:
        return ("identity_missing",)
    if (
        not isinstance(task, Mapping)
        or not _exact_keys(task, {"task_id", "attempt_id"})
        or not _texts(task, ("task_id", "attempt_id"))
    ):
        return ("identity_malformed",)
    if (
        not isinstance(repo, Mapping)
        or not _exact_keys(repo, {"repository", "source"})
        or not _texts(repo, ("repository", "source"))
    ):
        return ("identity_malformed",)
    if (
        not isinstance(base, Mapping)
        or not _exact_keys(base, {"commit", "tree"})
        or not _texts(base, ("commit", "tree"))
    ):
        return ("identity_malformed",)
    if (
        not isinstance(diff, Mapping)
        or not _exact_keys(diff, {"hash", "paths"})
        or not _hash(diff.get("hash"))
        or not _paths(diff.get("paths"))
    ):
        return ("identity_malformed",)
    if scope is None:
        return ("scope_missing",)
    if (
        not isinstance(scope, Mapping)
        or not _exact_keys(scope, {"paths", "deletion_policy"})
        or not _paths(scope.get("paths"))
        or scope.get("deletion_policy") not in {"FORBID", "ALLOW"}
    ):
        return ("scope_malformed",)
    if not set(diff["paths"]).issubset(scope["paths"]):
        return ("cross_binding_mismatch",)
    candidate = payload.get("candidate")
    if candidate is not None and (
        not isinstance(candidate, Mapping)
        or not _exact_keys(candidate, {"commit", "tree", "diff_hash"})
        or not _texts(candidate, ("commit", "tree"))
        or not _hash(candidate.get("diff_hash"))
    ):
        return ("candidate_malformed",)
    if candidate is not None and candidate["diff_hash"] != diff["hash"]:
        return ("cross_binding_mismatch",)
    manifest = payload.get("verifier_manifest")
    if manifest is None:
        return ("verifier_manifest_missing",)
    if (
        not isinstance(manifest, Mapping)
        or not _exact_keys(
            manifest,
            {
                "manifest_id",
                "task_id",
                "attempt_id",
                "source",
                "tree",
                "verifiers",
                "manifest_hash",
            },
        )
        or not _texts(manifest, ("manifest_id", "task_id", "attempt_id", "source", "tree"))
        or not _hash(manifest.get("manifest_hash"))
    ):
        return ("verifier_manifest_malformed",)
    if (manifest["task_id"], manifest["attempt_id"], manifest["source"], manifest["tree"]) != (
        task["task_id"],
        task["attempt_id"],
        repo["source"],
        base["tree"],
    ):
        return ("cross_binding_mismatch",)
    verifiers = manifest.get("verifiers")
    if not isinstance(verifiers, list) or not verifiers:
        return ("verifier_missing",)
    for verifier in verifiers:
        if not isinstance(verifier, Mapping):
            return ("verifier_artifact_malformed",)
        if (
            not _exact_keys(verifier, {"verifier_id", "artifact_id", "artifact_hash", "status"})
            or not _texts(verifier, ("verifier_id", "artifact_id"))
            or not _hash(verifier.get("artifact_hash"))
        ):
            return ("verifier_artifact_missing",)
        if verifier.get("status") not in _VERIFIER_STATUSES:
            return ("verifier_artifact_malformed",)
        if verifier["artifact_id"] != f"{verifier['verifier_id']}:{task['attempt_id']}":
            return ("cross_binding_mismatch",)
    reasons = payload.get("reasons")
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) or reason not in _REASONS for reason in reasons
    ):
        return ("reason_invalid",)
    if payload.get("disposition") not in _STATUSES:
        return ("status_invalid",)
    if payload.get("claim_ceiling") != CLAIM_CEILING:
        return ("cross_binding_mismatch",)
    if not _hash(payload.get("canonical_payload_hash")):
        return ("payload_hash_mismatch",)
    return ()


def _result(
    payload: Mapping[str, Any], status: CertificationStatus, reasons: tuple[str, ...]
) -> ChangeSetCertification:
    task = _mapping(payload.get("task"))
    base = _mapping(payload.get("base"))
    candidate = _mapping(payload.get("candidate"))
    diff = _mapping(payload.get("diff"))
    identity = ChangeSetIdentity(
        str(task.get("task_id", "")),
        str(base.get("commit", "")),
        str(candidate.get("commit", "")),
        str(diff.get("hash", "")),
    )
    result_payload = _copy(payload)
    result_payload["disposition"] = status.value
    result_payload["reasons"] = list(sorted(set(reasons)))
    return ChangeSetCertification(
        identity, status=status, reason_codes=tuple(sorted(set(reasons))), envelope=result_payload
    )


def _is_legacy(payload: Mapping[str, Any]) -> bool:
    return "task" not in payload


def _certify_legacy(payload: Mapping[str, Any]) -> ChangeSetCertification:
    identity = payload.get("change_set")
    if not isinstance(identity, Mapping):
        return _blocked("change_set_missing")
    if not _texts(identity, ("change_set_id", "source_revision", "target_revision")):
        return _rejected(("identity_malformed",), ChangeSetIdentity("", "", "", ""))
    if not _hash(identity.get("diff_hash")):
        return _rejected(("identity_diff_hash_invalid",), ChangeSetIdentity("", "", "", ""))
    parsed = ChangeSetIdentity(
        *(
            str(identity[k])
            for k in ("change_set_id", "source_revision", "target_revision", "diff_hash")
        )
    )
    evidence = payload.get("evidence")
    if evidence is None:
        return _blocked("evidence_missing", parsed)
    if not isinstance(evidence, (list, tuple)):
        return _rejected(("evidence_not_sequence",), parsed)
    if not evidence:
        return _blocked("evidence_empty", parsed)
    refs = tuple(
        EvidenceRef(
            str(item["evidence_id"]),
            str(item["kind"]),
            str(item["content_hash"]),
            str(item["source"]),
        )
        for item in evidence
        if isinstance(item, Mapping)
        and _texts(item, ("evidence_id", "kind", "source"))
        and _hash(item.get("content_hash"))
    )
    if len(refs) != len(evidence) or len({ref.evidence_id for ref in refs}) != len(refs):
        if any(
            not isinstance(item, Mapping)
            or not _texts(item, ("evidence_id", "kind", "source"))
            or not _hash(item.get("content_hash"))
            for item in evidence
        ):
            return _rejected(("evidence_0_invalid",), parsed)
        return _rejected(("evidence_duplicate_id",), parsed)
    result = ChangeSetCertification(parsed, refs, CertificationStatus.CERTIFIED)
    if payload.get("status") in {"BLOCKED", "REJECTED"}:
        return _rejected(("status_substitution",), parsed, refs)
    if (
        payload.get("canonical_hash") is not None
        and payload["canonical_hash"] != result.canonical_hash()
    ):
        return _rejected(("canonical_hash_mismatch",), parsed, refs)
    return result


def _legacy_wire(result: ChangeSetCertification) -> dict[str, Any]:
    return {
        "schema": result.schema,
        "status": result.status.value,
        "change_set": {
            "change_set_id": result.change_set.change_set_id,
            "source_revision": result.change_set.source_revision,
            "target_revision": result.change_set.target_revision,
            "diff_hash": result.change_set.diff_hash,
        },
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "content_hash": item.content_hash,
                "source": item.source,
            }
            for item in result.evidence
        ],
        "reason_codes": list(result.reason_codes),
        "claim_boundary": [
            "Certification describes supplied ChangeSet identities and evidence only.",
            "It does not apply a patch or authorize runtime, GitHub, provider, or shell actions.",
        ],
    }


def _payload_hash_input(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = _copy(payload)
    value.pop("canonical_payload_hash", None)
    return value


def _manifest_hash_input(manifest: Mapping[str, Any]) -> dict[str, Any]:
    value = _copy(manifest)
    value.pop("manifest_hash", None)
    return value


def _texts(value: Mapping[str, Any], keys: tuple[str, ...]) -> bool:
    return all(isinstance(value.get(key), str) and bool(value[key].strip()) for key in keys)


def _exact_keys(value: Mapping[str, Any], expected: set[str]) -> bool:
    return set(value) == expected


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _HASH_LEN
        and value.startswith("sha256:")
        and all(c in "0123456789abcdef" for c in value[7:].lower())
    )


def _paths(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and len(set(value)) == len(value)
        and all(isinstance(item, str) and item and not item.startswith("/") for item in value)
    )


def _normalize(value: Any, path: tuple[str, ...]) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("canonical JSON values must be finite")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON keys must be strings")
        return {key: _normalize(value[key], path + (key,)) for key in sorted(value)}
    if isinstance(value, list):
        normalized = [_normalize(item, path) for item in value]
        return (
            sorted(normalized, key=canonical_json)
            if path and path[-1] in {"paths", "reasons", "verifiers", "evidence"}
            else normalized
        )
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def _copy(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _blocked(reason: str, identity: ChangeSetIdentity | None = None) -> ChangeSetCertification:
    return ChangeSetCertification(
        identity or ChangeSetIdentity("", "", "", ""),
        status=CertificationStatus.BLOCKED,
        reason_codes=(reason,),
    )


def _rejected(
    reasons: tuple[str, ...], identity: ChangeSetIdentity, evidence: tuple[EvidenceRef, ...] = ()
) -> ChangeSetCertification:
    return ChangeSetCertification(
        identity, evidence, CertificationStatus.REJECTED, tuple(sorted(set(reasons)))
    )
