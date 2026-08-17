"""Provider-neutral, local ChangeSet certification contract.

This module deliberately contains no repository, runtime, provider, or shell
integration.  It only evaluates a fully materialised, caller-supplied
payload and returns a deterministic certification record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

CHANGESET_CERTIFICATION_SCHEMA = "nexus.changeset_certification.v1"
_STATUSES = {"CERTIFIED", "REJECTED", "BLOCKED"}
_SHA256_LENGTH = 64


class CertificationStatus(str, Enum):
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ChangeSetIdentity:
    """Stable identities that a certification is allowed to bind."""

    change_set_id: str
    source_revision: str
    target_revision: str
    diff_hash: str


@dataclass(frozen=True)
class EvidenceRef:
    """A content-addressed evidence reference; content is never loaded here."""

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
    schema: str = CHANGESET_CERTIFICATION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "status": self.status.value,
            "change_set": {
                "change_set_id": self.change_set.change_set_id,
                "source_revision": self.change_set.source_revision,
                "target_revision": self.change_set.target_revision,
                "diff_hash": self.change_set.diff_hash,
            },
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "kind": item.kind,
                    "content_hash": item.content_hash,
                    "source": item.source,
                }
                for item in self.evidence
            ],
            "reason_codes": list(self.reason_codes),
            "claim_boundary": [
                "Certification describes supplied ChangeSet identities and evidence only.",
                "It does not apply a patch or authorize runtime, GitHub, provider, or shell actions.",
            ],
        }
        return payload

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    def canonical_hash(self) -> str:
        return canonical_hash(self.to_dict())


def canonical_json(value: Any) -> str:
    """Return deterministic JSON, rejecting values that could stringify ambiguously."""
    _assert_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_hash(value: Any) -> str:
    """Return the SHA-256 of :func:`canonical_json` with an explicit algorithm prefix."""
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def certify_changeset(payload: Mapping[str, Any]) -> ChangeSetCertification:
    """Evaluate a caller-supplied payload without reading or mutating anything.

    Missing required material is ``BLOCKED``.  A present but malformed or
    contradictory identity/evidence claim is ``REJECTED``.  Only a complete,
    internally consistent payload becomes ``CERTIFIED``.
    """
    if not isinstance(payload, Mapping):
        return _blocked("payload_not_mapping")

    identity = payload.get("change_set")
    if not isinstance(identity, Mapping):
        return _blocked("change_set_missing")
    parsed, identity_errors = _parse_identity(identity)
    if parsed is None:
        return _rejected(identity_errors, _identity_placeholder(identity))

    raw_evidence = payload.get("evidence")
    if raw_evidence is None:
        return _blocked("evidence_missing", parsed)
    if not isinstance(raw_evidence, (list, tuple)):
        return _rejected(("evidence_not_sequence",), parsed)
    evidence, evidence_errors = _parse_evidence(raw_evidence)
    if evidence_errors:
        return _rejected(evidence_errors, parsed)
    if not evidence:
        return _blocked("evidence_empty", parsed)

    expected_status = payload.get("status")
    if expected_status is not None and (
        not isinstance(expected_status, str) or expected_status not in _STATUSES
    ):
        return _rejected(("status_invalid",), parsed, evidence)
    supplied_hash = payload.get("canonical_hash")
    result = ChangeSetCertification(
        change_set=parsed,
        evidence=tuple(evidence),
        status=CertificationStatus.CERTIFIED,
        reason_codes=(),
    )
    if supplied_hash is not None and supplied_hash != result.canonical_hash():
        return _rejected(("canonical_hash_mismatch",), parsed, evidence)
    if expected_status in {"REJECTED", "BLOCKED"}:
        return _rejected(("status_substitution",), parsed, evidence)
    return result


def build_changeset_certification(
    *,
    change_set: Mapping[str, Any],
    evidence: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None,
) -> dict[str, Any]:
    """Convenience wrapper returning the stable wire representation."""
    return certify_changeset({"change_set": change_set, "evidence": evidence}).to_dict()


def validate_changeset_certification(
    certification: ChangeSetCertification | Mapping[str, Any],
) -> tuple[str, ...]:
    """Validate a certification record, including its status/evidence boundary."""
    payload = (
        certification.to_dict()
        if isinstance(certification, ChangeSetCertification)
        else certification
    )
    if not isinstance(payload, Mapping):
        return ("certification_not_mapping",)
    if payload.get("schema") != CHANGESET_CERTIFICATION_SCHEMA:
        return ("schema_invalid",)
    status = payload.get("status")
    if status not in _STATUSES:
        return ("status_invalid",)
    if status == "CERTIFIED":
        if not isinstance(payload.get("change_set"), Mapping):
            return ("change_set_missing",)
        if not payload.get("evidence"):
            return ("evidence_missing",)
        if payload.get("reason_codes"):
            return ("certified_reasons_present",)
    return ()


def _parse_identity(value: Mapping[str, Any]) -> tuple[ChangeSetIdentity | None, tuple[str, ...]]:
    names = ("change_set_id", "source_revision", "target_revision", "diff_hash")
    errors = tuple(
        f"identity_{name}_invalid"
        for name in names
        if not _sha_or_text(value.get(name), name == "diff_hash")
    )
    if errors:
        return None, errors
    return ChangeSetIdentity(*(str(value[name]) for name in names)), ()


def _parse_evidence(
    values: list[Any] | tuple[Any, ...],
) -> tuple[list[EvidenceRef], tuple[str, ...]]:
    parsed: list[EvidenceRef] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            errors.append(f"evidence_{index}_not_mapping")
            continue
        fields = ("evidence_id", "kind", "content_hash", "source")
        if any(not _sha_or_text(value.get(name), name == "content_hash") for name in fields):
            errors.append(f"evidence_{index}_invalid")
            continue
        item = EvidenceRef(*(str(value[name]) for name in fields))
        if item.evidence_id in seen:
            errors.append("evidence_duplicate_id")
        seen.add(item.evidence_id)
        parsed.append(item)
    return parsed, tuple(sorted(set(errors)))


def _sha_or_text(value: Any, is_hash: bool) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if not is_hash:
        return True
    raw = value.removeprefix("sha256:")
    return len(raw) == _SHA256_LENGTH and all(char in "0123456789abcdef" for char in raw.lower())


def _blocked(reason: str, identity: ChangeSetIdentity | None = None) -> ChangeSetCertification:
    return ChangeSetCertification(
        change_set=identity or ChangeSetIdentity("", "", "", ""),
        status=CertificationStatus.BLOCKED,
        reason_codes=(reason,),
    )


def _rejected(
    reasons: tuple[str, ...],
    identity: ChangeSetIdentity,
    evidence: list[EvidenceRef] | tuple[EvidenceRef, ...] = (),
) -> ChangeSetCertification:
    return ChangeSetCertification(
        change_set=identity,
        evidence=tuple(evidence),
        status=CertificationStatus.REJECTED,
        reason_codes=tuple(sorted(set(reasons))),
    )


def _identity_placeholder(value: Mapping[str, Any]) -> ChangeSetIdentity:
    return ChangeSetIdentity(
        change_set_id=str(value.get("change_set_id") or ""),
        source_revision=str(value.get("source_revision") or ""),
        target_revision=str(value.get("target_revision") or ""),
        diff_hash=str(value.get("diff_hash") or ""),
    )


def _assert_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON keys must be strings")
            _assert_json_value(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_value(item)
        return
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")
