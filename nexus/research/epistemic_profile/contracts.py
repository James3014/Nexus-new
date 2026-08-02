from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

EPISTEMIC_ARTIFACT_REF_SCHEMA = "nexus.epistemic_artifact_ref.v0"
EPISTEMIC_EVIDENCE_RECORD_SCHEMA = "nexus.epistemic_evidence_record.v0"
EPISTEMIC_PROFILE_INPUT_SCHEMA = "nexus.epistemic_profile_input.v0"
EPISTEMIC_VERIFICATION_RESULT_SCHEMA = "nexus.epistemic_verification_result.v0"
EPISTEMIC_RECEIPT_EXTENSION_SCHEMA = "nexus.epistemic_receipt_extension.v0"


class EpistemicDirection(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUAL = "contextual"
    UNKNOWN = "unknown"


class EpistemicScopeAlignment(str, Enum):
    MATCHED = "matched"
    PARTIAL = "partial"
    MISMATCHED = "mismatched"
    UNKNOWN = "unknown"


class EpistemicIntegrityStatus(str, Enum):
    PASS = "PASS"
    RETURN = "RETURN"


_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class EpistemicArtifactRef:
    artifact_id: str
    content_sha256: str
    relative_ref: str
    lineage_ref: str = ""
    lineage_independence: str = "unknown"
    schema: str = EPISTEMIC_ARTIFACT_REF_SCHEMA

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.artifact_id.strip():
            raise ValueError("artifact_id must be non-empty")
        if not self.content_sha256 or not _SHA256_HEX_RE.match(self.content_sha256):
            raise ValueError("content_sha256 must be a 64-character lowercase hex string")
        if not self.relative_ref or not self.relative_ref.strip():
            raise ValueError("relative_ref must be a non-empty relative reference")
        if self.relative_ref.startswith("/"):
            raise ValueError("relative_ref must be a relative reference, not absolute")
        if ".." in self.relative_ref.split("/"):
            raise ValueError("relative_ref cannot contain path traversal ('..')")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "artifact_id": self.artifact_id,
            "content_sha256": self.content_sha256,
            "relative_ref": self.relative_ref,
            "lineage_ref": self.lineage_ref,
            "lineage_independence": self.lineage_independence,
        }


@dataclass(frozen=True)
class EpistemicEvidenceRecord:
    run_id: str
    claim_id: str
    artifact: EpistemicArtifactRef
    extraction_ref: str
    assessment_ref: str
    direction: EpistemicDirection = EpistemicDirection.UNKNOWN
    scope_alignment: EpistemicScopeAlignment = EpistemicScopeAlignment.UNKNOWN
    cannot_establish_present: bool = False
    evidence_hash_status: str = "PASS"
    evidence_seal_status: str = "PASS"
    receipt_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    schema: str = EPISTEMIC_EVIDENCE_RECORD_SCHEMA

    def __post_init__(self) -> None:
        if not self.run_id or not self.run_id.strip():
            raise ValueError("run_id must be non-empty")
        if not self.claim_id or not self.claim_id.strip():
            raise ValueError("claim_id must be non-empty")
        if not self.extraction_ref or not self.extraction_ref.strip():
            raise ValueError("extraction_ref must be non-empty")
        if not self.assessment_ref or not self.assessment_ref.strip():
            raise ValueError("assessment_ref must be non-empty")
        if self.direction in {EpistemicDirection.SUPPORTS, EpistemicDirection.CONTRADICTS}:
            if not self.cannot_establish_present:
                raise ValueError("cannot_establish_present must be True for supports or contradicts direction")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "claim_id": self.claim_id,
            "artifact": self.artifact.to_dict(),
            "extraction_ref": self.extraction_ref,
            "assessment_ref": self.assessment_ref,
            "direction": self.direction.value,
            "scope_alignment": self.scope_alignment.value,
            "cannot_establish_present": self.cannot_establish_present,
            "evidence_hash_status": self.evidence_hash_status,
            "evidence_seal_status": self.evidence_seal_status,
            "receipt_refs": list(self.receipt_refs),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class EpistemicProfileInput:
    task_id: str
    attempt_id: str
    profile_id: str
    run_id: str
    masked_brief_ref: str
    position_commitment_ref: str
    records: tuple[EpistemicEvidenceRecord, ...] = ()
    completion_status: str = "NOT_APPLICABLE"
    completion_envelope_ref: str = ""
    schema: str = EPISTEMIC_PROFILE_INPUT_SCHEMA

    def __post_init__(self) -> None:
        if not self.masked_brief_ref or not self.masked_brief_ref.strip():
            raise ValueError("masked_brief_ref must be non-empty")
        if not self.position_commitment_ref or not self.position_commitment_ref.strip():
            raise ValueError("position_commitment_ref must be non-empty")
        for rec in self.records:
            if rec.run_id != self.run_id:
                raise ValueError(f"record run_id mismatch: {rec.run_id} != {self.run_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "profile_id": self.profile_id,
            "run_id": self.run_id,
            "masked_brief_ref": self.masked_brief_ref,
            "position_commitment_ref": self.position_commitment_ref,
            "records": [rec.to_dict() for rec in self.records],
            "completion_status": self.completion_status,
            "completion_envelope_ref": self.completion_envelope_ref,
        }


@dataclass(frozen=True)
class EpistemicVerificationResult:
    status: EpistemicIntegrityStatus
    records_checked: int
    evidence_refs: tuple[str, ...]
    receipt_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    claim_evidence_read_model: dict[str, Any]
    schema: str = EPISTEMIC_VERIFICATION_RESULT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status.value,
            "records_checked": self.records_checked,
            "evidence_refs": list(self.evidence_refs),
            "receipt_refs": list(self.receipt_refs),
            "blockers": list(self.blockers),
            "claim_evidence_read_model": self.claim_evidence_read_model,
        }


@dataclass(frozen=True)
class EpistemicReceiptExtension:
    profile_id: str
    run_id: str
    records_checked: int = 0
    evidence_refs: tuple[str, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    claim_boundary: Any = None
    schema: str = EPISTEMIC_RECEIPT_EXTENSION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        boundary_dict = self.claim_boundary.to_dict() if self.claim_boundary and hasattr(self.claim_boundary, "to_dict") else {}
        return {
            "schema": self.schema,
            "profile_id": self.profile_id,
            "run_id": self.run_id,
            "records_checked": self.records_checked,
            "evidence_refs": list(self.evidence_refs),
            "receipt_refs": list(self.receipt_refs),
            "blockers": list(self.blockers),
            "claim_boundary": boundary_dict,
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "public_claim_allowed": False,
            "production_ready": False,
            "integration_approved": False,
        }
