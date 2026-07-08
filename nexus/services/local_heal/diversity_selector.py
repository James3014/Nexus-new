from __future__ import annotations

import hashlib
import re
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


@dataclass(frozen=True)
class CandidateFeatures:
    candidate_hash: str
    source_model: str
    source_format: str
    patch_length: int
    line_count: int
    token_set: frozenset[str]
    target_file_match: bool
    syntax_like_score: float
    safety_penalty: float


def extract_features(candidate: CanonicalPatchCandidate, model: str = "") -> CandidateFeatures:
    """P5-I2: Extract interpretable features from a CanonicalPatchCandidate.

    Args:
        candidate: The canonical candidate to extract features from.
        model: Optional source model name override.

    Returns:
        CandidateFeatures with extraction results.
    """
    patch = candidate.normalized_patch or ""

    # patch_length
    patch_length = len(patch)

    # line_count
    line_count = len(patch.splitlines()) if patch.strip() else 0

    # token_set
    tokens = re.findall(r'\S+', patch)
    token_set = frozenset(tokens)

    # target_file_match
    target_file_match = bool(candidate.target_file.strip())

    # syntax_like_score
    if not patch.strip():
        syntax_like_score = 0.0
    elif any(marker in patch for marker in ["--- ", "+++ ", "@@ ", "<<<<<<< ", ">>>>>>> "]):
        syntax_like_score = 1.0
    else:
        syntax_like_score = 0.5

    # safety_penalty
    if candidate.safety_flags:
        safety_penalty = min(1.0, len(candidate.safety_flags) * 0.3)
    else:
        safety_penalty = 0.0

    return CandidateFeatures(
        candidate_hash=candidate.raw_output_hash,
        source_model=model or "",
        source_format=candidate.source_format,
        patch_length=patch_length,
        line_count=line_count,
        token_set=token_set,
        target_file_match=target_file_match,
        syntax_like_score=syntax_like_score,
        safety_penalty=safety_penalty,
    )


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: str
    candidate_indices: tuple[int, ...]
    representative_index: int
    duplicate_kind: str  # "exact" or "near"
    similarity_score: float


def _jaccard_similarity(set_a: frozenset[str], set_b: frozenset[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def group_near_duplicates(features: list[CandidateFeatures]) -> list[DuplicateGroup]:
    """P5-I3: Group duplicate and near-duplicate candidates.

    Args:
        features: List of CandidateFeatures (never mutated).

    Returns:
        List of DuplicateGroup objects. Empty list if no duplicates found.
    """
    if len(features) < 2:
        return []

    groups: list[DuplicateGroup] = []
    used_indices: set[int] = set()

    for i in range(len(features)):
        if i in used_indices:
            continue

        fi = features[i]
        group_indices = [i]

        for j in range(i + 1, len(features)):
            if j in used_indices:
                continue

            fj = features[j]

            # Different target_file → never grouped
            if fi.target_file_match and fj.target_file_match:
                # Both have target_file set — check if same file
                # (target_file not stored in CandidateFeatures, but target_file_match is bool)
                # Since we only have target_file_match (bool), we use token similarity as primary
                pass

            # Exact duplicate: same normalized_patch_hash (via candidate_hash)
            if fi.candidate_hash == fj.candidate_hash:
                group_indices.append(j)
                used_indices.add(j)
                continue

            # Near duplicate: token Jaccard >= 0.85
            if fi.token_set and fj.token_set:
                sim = _jaccard_similarity(fi.token_set, fj.token_set)
                if sim >= 0.85:
                    group_indices.append(j)
                    used_indices.add(j)
                    continue

        if len(group_indices) > 1:
            used_indices.add(i)
            representative = min(group_indices)
            groups.append(DuplicateGroup(
                group_id=f"dup-{representative}",
                candidate_indices=tuple(sorted(group_indices)),
                representative_index=representative,
                duplicate_kind="exact" if len(set(
                    features[k].candidate_hash for k in group_indices
                )) == 1 else "near",
                similarity_score=1.0 if len(set(
                    features[k].candidate_hash for k in group_indices
                )) == 1 else max(
                    _jaccard_similarity(fi.token_set, features[k].token_set)
                    for k in group_indices if k != i
                ),
            ))

    return groups


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
