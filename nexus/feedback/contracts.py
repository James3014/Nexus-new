"""Codes-and-references contract for durable developer feedback decisions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

DECISION_SCHEMA = "nexus.developer_feedback_decision.v1"
DECISIONS = frozenset({"KEEP", "REVISE", "REJECT", "INVESTIGATE"})
DELTA_TYPES = frozenset({"SPEC", "EVAL", "PRODUCT_ASSUMPTION"})
DESTINATIONS = frozenset(
    {
        "NO_FOLLOW_UP",
        "SPEC_DELTA_REQUESTED",
        "EVAL_DELTA_REQUESTED",
        "PRODUCT_ASSUMPTION_DELTA_REQUESTED",
        "CANDIDATE_REJECTION_RECORDED",
        "INVESTIGATION_REQUESTED",
    }
)
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_BIDI = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u200e\u200f")
_FIELDS = frozenset(
    {
        "schema",
        "decision_id",
        "task_id",
        "attempt_id",
        "action",
        "candidate_ref",
        "candidate_digest",
        "evidence_refs",
        "source_revision",
        "source_tree",
        "evidence_hash",
        "decision",
        "rationale_codes",
        "delta_type",
        "delta_codes",
        "acceptance_surface",
        "approver_ref",
        "repository_ref",
        "approved_at",
        "idempotency_key",
        "expected_task_seq",
        "expected_parent_digest",
        "follow_up_destination_ref",
    }
)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _token(value: str, name: str, *, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not value and allow_empty is False)
        or len(value) > 128
        or not _TOKEN.fullmatch(value)
    ):
        raise ValueError(f"invalid_{name}")
    if any(ord(c) < 32 or ord(c) == 127 or c in _BIDI for c in value):
        raise ValueError(f"invalid_{name}")
    if "/" in value or "\\" in value or "@" in value or "?" in value or "#" in value:
        raise ValueError(f"invalid_{name}")
    return value


def _hash(value: str, name: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"invalid_{name}")
    return value


@dataclass(frozen=True)
class DeveloperFeedbackDecisionRequest:
    decision_id: str
    task_id: str
    attempt_id: str
    action: str
    evidence_refs: tuple[str, ...]
    source_revision: str
    source_tree: str
    evidence_hash: str
    decision: Literal["KEEP", "REVISE", "REJECT", "INVESTIGATE"]
    rationale_codes: tuple[str, ...]
    approver_ref: str
    repository_ref: str
    approved_at: str
    idempotency_key: str
    candidate_ref: str | None = None
    candidate_digest: str | None = None
    delta_type: str | None = None
    delta_codes: tuple[str, ...] = ()
    acceptance_surface: str | None = None
    expected_task_seq: int | None = None
    expected_parent_digest: str | None = None
    follow_up_destination_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "rationale_codes", tuple(self.rationale_codes))
        object.__setattr__(self, "delta_codes", tuple(self.delta_codes))
        validate_request(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            k: v
            for k, v in {
                "schema": DECISION_SCHEMA,
                "decision_id": self.decision_id,
                "task_id": self.task_id,
                "attempt_id": self.attempt_id,
                "action": self.action,
                "candidate_ref": self.candidate_ref,
                "candidate_digest": self.candidate_digest,
                "evidence_refs": list(self.evidence_refs),
                "source_revision": self.source_revision,
                "source_tree": self.source_tree,
                "evidence_hash": self.evidence_hash,
                "decision": self.decision,
                "rationale_codes": list(self.rationale_codes),
                "delta_type": self.delta_type,
                "delta_codes": list(self.delta_codes),
                "acceptance_surface": self.acceptance_surface,
                "approver_ref": self.approver_ref,
                "repository_ref": self.repository_ref,
                "approved_at": self.approved_at,
                "idempotency_key": self.idempotency_key,
                "expected_task_seq": self.expected_task_seq,
                "expected_parent_digest": self.expected_parent_digest,
                "follow_up_destination_ref": self.follow_up_destination_ref,
            }.items()
            if v is not None
        }


def validate_request(request: DeveloperFeedbackDecisionRequest) -> None:
    for name in (
        "decision_id",
        "task_id",
        "attempt_id",
        "action",
        "source_revision",
        "source_tree",
        "approver_ref",
        "repository_ref",
        "approved_at",
        "idempotency_key",
    ):
        _token(getattr(request, name), name)
    if request.decision not in DECISIONS:
        raise ValueError("invalid_decision")
    if not 1 <= len(request.evidence_refs) <= 32 or not 1 <= len(request.rationale_codes) <= 16:
        raise ValueError("invalid_reference_count")
    if len(request.delta_codes) > 16:
        raise ValueError("invalid_delta_count")
    for value in (*request.evidence_refs, *request.rationale_codes, *request.delta_codes):
        _token(value, "code_or_ref")
    _hash(request.evidence_hash, "evidence_hash")
    if request.candidate_ref is not None:
        _token(request.candidate_ref, "candidate_ref")
    if request.candidate_digest is not None:
        _hash(request.candidate_digest, "candidate_digest")
    if request.expected_parent_digest is not None:
        _hash(request.expected_parent_digest, "expected_parent_digest")
    if request.expected_task_seq is not None and (
        not isinstance(request.expected_task_seq, int) or request.expected_task_seq < 0
    ):
        raise ValueError("invalid_expected_task_seq")
    if request.delta_type not in DELTA_TYPES | {None}:
        raise ValueError("invalid_delta_type")
    if request.acceptance_surface is not None:
        _token(request.acceptance_surface, "acceptance_surface")
    if request.follow_up_destination_ref is not None:
        _token(request.follow_up_destination_ref, "follow_up_destination_ref")
    if request.decision == "KEEP" and request.delta_type is not None:
        raise ValueError("keep_cannot_have_delta")
    if request.decision == "REVISE" and request.delta_type is None:
        raise ValueError("revise_requires_delta")
    if request.decision == "REJECT" and (not request.candidate_ref or not request.candidate_digest):
        raise ValueError("reject_requires_candidate")
    if request.decision == "INVESTIGATE" and request.delta_type is not None:
        raise ValueError("investigate_cannot_have_delta")


def request_digest(request: DeveloperFeedbackDecisionRequest) -> str:
    return _digest(request.to_dict())


def decision_mapping(request: DeveloperFeedbackDecisionRequest) -> str:
    validate_request(request)
    if request.decision == "KEEP":
        return "NO_FOLLOW_UP"
    if request.decision == "REVISE":
        return f"{request.delta_type}_DELTA_REQUESTED"
    if request.decision == "REJECT":
        return "CANDIDATE_REJECTION_RECORDED"
    return "INVESTIGATION_REQUESTED"


def with_chain(
    request: DeveloperFeedbackDecisionRequest, *, task_seq: int, parent_digest: str | None
) -> dict[str, Any]:
    destination = decision_mapping(request)
    body = request.to_dict() | {
        "next_gate": destination,
        "task_seq": task_seq,
        "parent_digest": parent_digest,
    }
    body["request_digest"] = request_digest(request)
    body["record_digest"] = _digest(body)
    return body


DeveloperFeedbackDecision = DeveloperFeedbackDecisionRequest
