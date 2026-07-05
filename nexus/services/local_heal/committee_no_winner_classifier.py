"""B2: Committee no-winner failure classifier.

Classifies committee_no_winner into bounded failure classes using existing telemetry.
No route authority, no parser relaxation, no verifier weakening.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FAILURE_CLASSES = (
    "OUTPUT_QUALITY_CEILING",
    "FORMAT_CONVERSION_GAP",
    "CANDIDATE_ISOLATION_GAP",
    "VERIFIER_EVIDENCE_GAP",
    "UNKNOWN_NEEDS_INSTRUMENTATION",
)


@dataclass(frozen=True)
class CommitteeClassification:
    failure_class: str
    evidence: str
    candidate_count: int
    has_winner: bool
    classification_available: bool


def classify_committee_no_winner(
    candidates: list[dict[str, Any]] | None = None,
    winner: dict[str, Any] | None = None,
) -> CommitteeClassification:
    """Classify committee_no_winner into bounded failure classes.

    Classification schema:
    - OUTPUT_QUALITY_CEILING: all candidates have empty/very short patches
    - FORMAT_CONVERSION_GAP: candidates have patches but all fail format validation
    - CANDIDATE_ISOLATION_GAP: candidates exist but isolation check failed
    - VERIFIER_EVIDENCE_GAP: candidates pass format but verifier evidence missing
    - UNKNOWN_NEEDS_INSTRUMENTATION: insufficient telemetry to classify
    """
    if winner is not None:
        return CommitteeClassification(
            failure_class="UNKNOWN_NEEDS_INSTRUMENTATION",
            evidence="winner exists — not a no_winner case",
            candidate_count=len(candidates or []),
            has_winner=True,
            classification_available=False,
        )

    if not candidates:
        return CommitteeClassification(
            failure_class="UNKNOWN_NEEDS_INSTRUMENTATION",
            evidence="no candidates provided",
            candidate_count=0,
            has_winner=False,
            classification_available=False,
        )

    candidate_count = len(candidates)

    # Check for OUTPUT_QUALITY_CEILING: all patches empty or very short
    patches = [str(c.get("candidate_patch", "") or "") for c in candidates]
    non_empty_patches = [p for p in patches if len(p.strip()) > 10]
    if not non_empty_patches:
        return CommitteeClassification(
            failure_class="OUTPUT_QUALITY_CEILING",
            evidence=f"all {candidate_count} candidates have empty/short patches",
            candidate_count=candidate_count,
            has_winner=False,
            classification_available=True,
        )

    # Check for FORMAT_CONVERSION_GAP: all candidates have format_rejected status
    apply_statuses = {str(c.get("apply_status", "") or "") for c in candidates}
    if apply_statuses == {"format_rejected"} or all(
        "format_rejected" in str(c.get("apply_status", "") or "") for c in candidates
    ):
        return CommitteeClassification(
            failure_class="FORMAT_CONVERSION_GAP",
            evidence=f"all {candidate_count} candidates have format_rejected status",
            candidate_count=candidate_count,
            has_winner=False,
            classification_available=True,
        )

    # Check for CANDIDATE_ISOLATION_GAP: isolation check failed
    rejection_reasons = {str(c.get("rejection_reason", "") or "") for c in candidates}
    isolation_reasons = {"isolation_applied_hash_mismatch", "isolation_check_failed"}
    if rejection_reasons & isolation_reasons:
        return CommitteeClassification(
            failure_class="CANDIDATE_ISOLATION_GAP",
            evidence=f"isolation rejection reasons: {rejection_reasons & isolation_reasons}",
            candidate_count=candidate_count,
            has_winner=False,
            classification_available=True,
        )

    # Check for VERIFIER_EVIDENCE_GAP: verifier evidence missing
    verifier_evidence_present = any(
        bool(c.get("verifier_evidence") or c.get("evidence_refs")) for c in candidates
    )
    if not verifier_evidence_present and non_empty_patches:
        return CommitteeClassification(
            failure_class="VERIFIER_EVIDENCE_GAP",
            evidence=f"{len(non_empty_patches)} candidates have patches but no verifier evidence",
            candidate_count=candidate_count,
            has_winner=False,
            classification_available=True,
        )

    # Insufficient telemetry to classify
    return CommitteeClassification(
        failure_class="UNKNOWN_NEEDS_INSTRUMENTATION",
        evidence=f"{candidate_count} candidates with patches but no clear failure pattern",
        candidate_count=candidate_count,
        has_winner=False,
        classification_available=False,
    )
