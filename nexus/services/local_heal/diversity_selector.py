from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


@dataclass(frozen=True)
class DiversityCandidate:
    candidate_id: str
    candidate_hash: str
    source_model: str
    source_format: str
    target_file: str
    target_symbol: str
    normalized_patch: str
    normalized_patch_hash: str
    raw_output_hash: str
    safety_flags: tuple[str, ...]
    canonical_index: int

    @classmethod
    def from_canonical(
        cls,
        candidate: CanonicalPatchCandidate,
        *,
        index: int,
        source_model: str = "",
    ) -> DiversityCandidate:
        raw_id = f"{candidate.raw_output_hash[:16]}#{index}"
        return cls(
            candidate_id=raw_id,
            candidate_hash=candidate.raw_output_hash,
            source_model=source_model,
            source_format=candidate.source_format,
            target_file=candidate.target_file,
            target_symbol=candidate.target_symbol,
            normalized_patch=candidate.normalized_patch,
            normalized_patch_hash=candidate.normalized_patch_hash,
            raw_output_hash=candidate.raw_output_hash,
            safety_flags=candidate.safety_flags,
            canonical_index=index,
        )


@dataclass(frozen=True)
class DiversitySelectionResult:
    selected_candidate_id: str
    selected_candidate_hash: str
    selected_index: int
    selection_strategy: str
    candidate_count: int
    diversity_candidate_count: int
    duplicate_group_count: int
    popularity_trap_detected: bool
    popularity_trap_reason: str
    score_breakdown: list[dict[str, Any]]
    rejected_by_diversity: list[dict[str, Any]]
    fail_closed: bool
    failure_reasons: list[str]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_candidate_id(candidate: CanonicalPatchCandidate, index: int) -> str:
    return f"{candidate.raw_output_hash[:16]}#{index}"


def select_diverse_candidate(
    candidates: list[CanonicalPatchCandidate],
    *,
    source_models: list[str] | None = None,
    strategy: str = "diversity_v1",
) -> DiversitySelectionResult:
    """P5-I1: Select the most diverse candidate from a list of valid candidates.

    This is the contract-only implementation (P5-I1). It does NOT yet perform
    diversity-aware selection — it returns the first valid candidate and records
    the strategy. Future P5 iterations will upgrade selectivity.

    Args:
        candidates: Valid CanonicalPatchCandidate list (already adapted).
        source_models: Optional source model names per candidate index.
        strategy: Selection strategy name. I1 accepts "diversity_v1".

    Returns:
        DiversitySelectionResult with selection decision and explainability fields.
    """
    if source_models is None:
        source_models = [""] * len(candidates)

    # Empty candidates → fail closed
    if not candidates:
        return DiversitySelectionResult(
            selected_candidate_id="",
            selected_candidate_hash="",
            selected_index=-1,
            selection_strategy=strategy,
            candidate_count=0,
            diversity_candidate_count=0,
            duplicate_group_count=0,
            popularity_trap_detected=False,
            popularity_trap_reason="",
            score_breakdown=[],
            rejected_by_diversity=[],
            fail_closed=True,
            failure_reasons=["no_candidates"],
        )

    # Single candidate
    if len(candidates) == 1:
        cid = _build_candidate_id(candidates[0], 0)
        return DiversitySelectionResult(
            selected_candidate_id=cid,
            selected_candidate_hash=candidates[0].raw_output_hash,
            selected_index=0,
            selection_strategy="single_candidate",
            candidate_count=1,
            diversity_candidate_count=1,
            duplicate_group_count=0,
            popularity_trap_detected=False,
            popularity_trap_reason="",
            score_breakdown=[{"candidate_id": cid, "index": 0, "strategy": "single_candidate"}],
            rejected_by_diversity=[],
            fail_closed=False,
            failure_reasons=[],
        )

    # Multiple candidates — contract-only: select first valid
    cid = _build_candidate_id(candidates[0], 0)
    return DiversitySelectionResult(
        selected_candidate_id=cid,
        selected_candidate_hash=candidates[0].raw_output_hash,
        selected_index=0,
        selection_strategy="contract_only_first_valid",
        candidate_count=len(candidates),
        diversity_candidate_count=len(candidates),
        duplicate_group_count=0,
        popularity_trap_detected=False,
        popularity_trap_reason="",
        score_breakdown=[
            {"candidate_id": cid, "index": 0, "strategy": "contract_only_first_valid"},
        ],
        rejected_by_diversity=[],
        fail_closed=False,
        failure_reasons=[],
    )
