"""Independent, non-promoting acceptance of an exact Candidate."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping

from nexus.services.local_heal.verified_repair import reduce_verified_repair

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")


class AcceptanceDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REPAIRABLE = "REPAIRABLE"
    BLOCK = "BLOCK"


def _identity(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _hash(value: str, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{field} has invalid hash format")
    return value


@dataclass(frozen=True)
class CandidateAcceptanceRequest:
    task_id: str
    attempt_id: str
    implementer_id: str
    candidate_commit_sha: str
    candidate_tree_sha: str
    candidate_state_hash: str
    candidate_diff_hash: str
    verified_receipt_hash: str
    candidate_class: str = "GENERAL"
    schema: str = "nexus.candidate_acceptance_request.v1"

    def __post_init__(self) -> None:
        if self.schema != "nexus.candidate_acceptance_request.v1":
            raise ValueError("unsupported Candidate acceptance request schema")
        for field in ("task_id", "attempt_id", "implementer_id"):
            _identity(getattr(self, field), field)
        _hash(self.candidate_commit_sha, "candidate_commit_sha", _SHA40)
        _hash(self.candidate_tree_sha, "candidate_tree_sha", _SHA40)
        for field in ("candidate_state_hash", "candidate_diff_hash", "verified_receipt_hash"):
            _hash(getattr(self, field), field, _SHA64)
        if self.candidate_class not in {"GENERAL", "VERIFIED_REPAIR"}:
            raise ValueError("unsupported candidate_class")


@dataclass(frozen=True)
class IndependentReviewReceipt:
    task_id: str
    attempt_id: str
    reviewer_id: str
    candidate_commit_sha: str
    candidate_tree_sha: str
    candidate_state_hash: str
    candidate_diff_hash: str
    verified_receipt_hash: str
    verifier_artifact_hash: str
    review_status: str
    exit_code: int
    reasons: tuple[str, ...] = ()
    schema: str = "nexus.independent_candidate_review.v1"

    def __post_init__(self) -> None:
        if self.schema != "nexus.independent_candidate_review.v1":
            raise ValueError("unsupported independent review schema")
        for field in ("task_id", "attempt_id", "reviewer_id"):
            _identity(getattr(self, field), field)
        _hash(self.candidate_commit_sha, "candidate_commit_sha", _SHA40)
        _hash(self.candidate_tree_sha, "candidate_tree_sha", _SHA40)
        for field in (
            "candidate_state_hash",
            "candidate_diff_hash",
            "verified_receipt_hash",
            "verifier_artifact_hash",
        ):
            _hash(getattr(self, field), field, _SHA64)
        if self.review_status not in {"PASS", "DEFECT", "BLOCK"}:
            raise ValueError("unsupported review_status")
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise ValueError("exit_code must be an integer")
        if any(not isinstance(reason, str) or not reason.strip() for reason in self.reasons):
            raise ValueError("review reasons must be non-empty strings")


@dataclass(frozen=True)
class CandidateAcceptanceResult:
    decision: AcceptanceDecision
    task_id: str
    attempt_id: str
    candidate_commit_sha: str
    reviewer_id: str
    binding_hash: str
    reasons: tuple[str, ...]
    approval_performed: bool = False
    integration_performed: bool = False
    merge_performed: bool = False
    public_claim_allowed: bool = False
    schema: str = "nexus.candidate_acceptance_result.v1"

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["decision"] = self.decision.value
        value["reasons"] = list(self.reasons)
        return value


def _binding_hash(request: CandidateAcceptanceRequest, review: IndependentReviewReceipt) -> str:
    payload = {
        "request": asdict(request),
        "review": asdict(review),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def reduce_candidate_acceptance(
    request: CandidateAcceptanceRequest,
    review: IndependentReviewReceipt,
    *,
    verified_repair_evidence: Mapping[str, Any] | None = None,
) -> CandidateAcceptanceResult:
    """Reduce exact identities and existing #16 evidence without promoting."""
    reasons: list[str] = []
    if request.implementer_id == review.reviewer_id:
        reasons.append("reviewer_is_implementer")

    identity_fields = (
        "task_id",
        "attempt_id",
        "candidate_commit_sha",
        "candidate_tree_sha",
        "candidate_state_hash",
        "candidate_diff_hash",
        "verified_receipt_hash",
    )
    reasons.extend(
        f"{field}_mismatch"
        for field in identity_fields
        if getattr(request, field) != getattr(review, field)
    )
    binding = _binding_hash(request, review)

    if reasons or review.review_status == "BLOCK":
        reasons.extend(review.reasons or (("review_blocked",) if not reasons else ()))
        decision = AcceptanceDecision.BLOCK
    elif review.review_status == "DEFECT":
        decision = AcceptanceDecision.REPAIRABLE
        reasons.extend(review.reasons or ("independent_review_defect",))
    elif review.exit_code != 0:
        decision = AcceptanceDecision.BLOCK
        reasons.append("verifier_exit_nonzero")
    elif request.candidate_class == "VERIFIED_REPAIR":
        repair = reduce_verified_repair(verified_repair_evidence)
        if repair.get("status") != "VERIFIED_REPAIR":
            decision = AcceptanceDecision.BLOCK
            reasons.extend(f"verified_repair:{reason}" for reason in repair.get("reasons", ()))
        else:
            decision = AcceptanceDecision.ACCEPT
    else:
        decision = AcceptanceDecision.ACCEPT

    return CandidateAcceptanceResult(
        decision=decision,
        task_id=request.task_id,
        attempt_id=request.attempt_id,
        candidate_commit_sha=request.candidate_commit_sha,
        reviewer_id=review.reviewer_id,
        binding_hash=binding,
        reasons=tuple(dict.fromkeys(reasons)),
    )


__all__ = [
    "AcceptanceDecision",
    "CandidateAcceptanceRequest",
    "CandidateAcceptanceResult",
    "IndependentReviewReceipt",
    "reduce_candidate_acceptance",
]
