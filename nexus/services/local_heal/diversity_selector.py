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
    target_file: str = ""
    source_model: str = ""
    source_format: str = ""
    patch_length: int = 0
    line_count: int = 0
    token_set: frozenset[str] = field(default_factory=frozenset)
    target_file_match: bool = False
    syntax_like_score: float = 0.0
    safety_penalty: float = 0.0


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
        target_file=candidate.target_file or "",
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

            # Different target_file → never grouped (even if same hash)
            actual_target_i = fi.target_file or ""
            actual_target_j = fj.target_file or ""
            if actual_target_i and actual_target_j and actual_target_i != actual_target_j:
                continue

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


@dataclass(frozen=True)
class PopularityTrapDecision:
    detected: bool
    dominant_group_id: str
    dominant_group_size: int
    candidate_count: int
    reason: str
    recommended_action: str  # "penalize_dominant_group", "fail_closed", "none"


def detect_popularity_trap(
    features: list[CandidateFeatures],
    groups: list[DuplicateGroup],
) -> PopularityTrapDecision:
    """P5-I4: Detect popularity trap in candidate groups.

    Trap detected when dominant group has ANY:
    - target_file_match=False for any member
    - syntax_like_score < 0.5 for any member
    - safety_penalty > 0 for any member
    - group size > 50% of total AND all same source_model family
    """
    if not features or not groups:
        return PopularityTrapDecision(
            detected=False,
            dominant_group_id="",
            dominant_group_size=0,
            candidate_count=len(features),
            reason="no_groups",
            recommended_action="none",
        )

    # Find dominant group (largest)
    dominant = max(groups, key=lambda g: len(g.candidate_indices))
    dominant_size = len(dominant.candidate_indices)
    candidate_count = len(features)

    # Check trap conditions
    trap_reasons = []

    for idx in dominant.candidate_indices:
        if idx < len(features):
            fi = features[idx]
            if not fi.target_file_match:
                trap_reasons.append("dominant_group_has_missing_target_file")
            if fi.syntax_like_score < 0.5:
                trap_reasons.append("dominant_group_has_low_syntax_score")
            if fi.safety_penalty > 0:
                trap_reasons.append("dominant_group_has_safety_penalty")

    # Model homogeneity check
    if dominant_size > candidate_count / 2:
        models = set()
        for idx in dominant.candidate_indices:
            if idx < len(features):
                models.add(features[idx].source_model)
        if len(models) == 1 and any(models):
            trap_reasons.append("model_homogeneity")

    if not trap_reasons:
        return PopularityTrapDecision(
            detected=False,
            dominant_group_id=dominant.group_id,
            dominant_group_size=dominant_size,
            candidate_count=candidate_count,
            reason="no_trap",
            recommended_action="none",
        )

    # Determine action
    all_unsafe = all(
        features[idx].safety_penalty > 0 or features[idx].syntax_like_score < 0.5
        for idx in dominant.candidate_indices
        if idx < len(features)
    )

    if all_unsafe:
        action = "fail_closed"
    else:
        action = "penalize_dominant_group"

    return PopularityTrapDecision(
        detected=True,
        dominant_group_id=dominant.group_id,
        dominant_group_size=dominant_size,
        candidate_count=candidate_count,
        reason=";".join(trap_reasons),
        recommended_action=action,
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_candidate_id(candidate: CanonicalPatchCandidate, index: int) -> str:
    return f"{candidate.raw_output_hash[:16]}#{index}"


def _score_candidate(
    features: CandidateFeatures,
    index: int,
    all_features: list[CandidateFeatures],
    groups: list[DuplicateGroup],
    trap_decision: PopularityTrapDecision,
    dominant_models: set[str],
    majority_format: str,
) -> tuple[float, dict[str, Any]]:
    """P5-I5: Score a single candidate for diversity-aware selection.

    Returns (final_score, breakdown_dict).
    """
    # quality_score = syntax_like_score (range 0-1)
    quality_score = features.syntax_like_score

    # model_diversity_bonus = 0.2 per unique model not in dominant group
    model_diversity_bonus = 0.0
    if features.source_model and features.source_model not in dominant_models:
        model_diversity_bonus = 0.2

    # format_diversity_bonus = 0.1 if candidate format differs from majority
    format_diversity_bonus = 0.0
    if features.source_format != majority_format:
        format_diversity_bonus = 0.1

    # target_match_bonus = 0.3 if target_file_match else 0
    target_match_bonus = 0.3 if features.target_file_match else 0.0

    # duplicate_penalty = 0.2 per other candidate in same duplicate group
    duplicate_penalty = 0.0
    for group in groups:
        if index in group.candidate_indices:
            other_count = len(group.candidate_indices) - 1
            duplicate_penalty = 0.2 * other_count
            break

    # popularity_trap_penalty = 0.5 if dominant group is penalized and candidate is in it
    popularity_trap_penalty = 0.0
    if trap_decision.detected and trap_decision.recommended_action == "penalize_dominant_group":
        # Check if candidate is in dominant group
        for group in groups:
            if group.group_id == trap_decision.dominant_group_id:
                if index in group.candidate_indices:
                    popularity_trap_penalty = 0.5
                break

    # safety_penalty = CandidateFeatures.safety_penalty
    safety_penalty = features.safety_penalty

    final_score = (
        quality_score
        + model_diversity_bonus
        + format_diversity_bonus
        + target_match_bonus
        - duplicate_penalty
        - popularity_trap_penalty
        - safety_penalty
    )

    breakdown = {
        "candidate_id": features.candidate_hash[:16] + f"#{index}",
        "index": index,
        "source_model": features.source_model,
        "source_format": features.source_format,
        "quality_score": quality_score,
        "model_diversity_bonus": model_diversity_bonus,
        "format_diversity_bonus": format_diversity_bonus,
        "target_match_bonus": target_match_bonus,
        "duplicate_penalty": duplicate_penalty,
        "popularity_trap_penalty": popularity_trap_penalty,
        "safety_penalty": safety_penalty,
        "final_score": final_score,
    }

    return final_score, breakdown


def select_diverse_candidate(
    candidates: list[CanonicalPatchCandidate],
    *,
    source_models: list[str] | None = None,
    strategy: str = "diversity_v1",
) -> DiversitySelectionResult:
    """P5-I5: Select the most diverse candidate from a list of valid candidates.

    Scoring formula:
    final_score = quality_score + model_diversity_bonus + format_diversity_bonus
                 + target_match_bonus - duplicate_penalty - popularity_trap_penalty
                 - safety_penalty

    Tie-break: higher final_score → lower safety_penalty → non-dominant group → lower index.

    Args:
        candidates: Valid CanonicalPatchCandidate list (already adapted).
        source_models: Optional source model names per candidate index.
        strategy: Selection strategy name. "diversity_v1" enables diversity scoring.
                  "contract_only_first_valid" returns index 0 (backward compat).

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

    # Contract-only strategy: return first valid without scoring
    if strategy == "contract_only_first_valid":
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
            score_breakdown=[{"candidate_id": cid, "index": 0, "strategy": "contract_only_first_valid"}],
            rejected_by_diversity=[],
            fail_closed=False,
            failure_reasons=[],
        )

    # Extract features for all candidates
    all_features = [extract_features(c, source_models[i]) for i, c in enumerate(candidates)]

    # Group near-duplicates
    groups = group_near_duplicates(all_features)

    # Detect popularity trap
    trap_decision = detect_popularity_trap(all_features, groups)

    # Compute dominant models and majority format
    model_counts: dict[str, int] = {}
    for f in all_features:
        if f.source_model:
            model_counts[f.source_model] = model_counts.get(f.source_model, 0) + 1
    dominant_models = set()
    if model_counts:
        max_count = max(model_counts.values())
        dominant_models = {m for m, c in model_counts.items() if c == max_count}

    format_counts: dict[str, int] = {}
    for f in all_features:
        format_counts[f.source_format] = format_counts.get(f.source_format, 0) + 1
    majority_format = max(format_counts, key=format_counts.get) if format_counts else ""

    # Score all candidates
    scored: list[tuple[float, int, dict[str, Any], CandidateFeatures]] = []
    for i, (c, f) in enumerate(zip(candidates, all_features)):
        final_score, breakdown = _score_candidate(
            f, i, all_features, groups, trap_decision, dominant_models, majority_format,
        )
        scored.append((final_score, i, breakdown, f))

    # Check if ALL candidates have final_score <= 0
    all_unsafe = all(s[0] <= 0 for s in scored)
    if all_unsafe:
        cid = _build_candidate_id(candidates[0], 0)
        return DiversitySelectionResult(
            selected_candidate_id=cid,
            selected_candidate_hash=candidates[0].raw_output_hash,
            selected_index=0,
            selection_strategy="diversity_v1",
            candidate_count=len(candidates),
            diversity_candidate_count=len(candidates),
            duplicate_group_count=len(groups),
            popularity_trap_detected=trap_decision.detected,
            popularity_trap_reason=trap_decision.reason,
            score_breakdown=[s[2] for s in scored],
            rejected_by_diversity=list(range(len(candidates))),
            fail_closed=True,
            failure_reasons=["all_candidates_unsafe"],
        )

    # Sort: higher final_score first, then lower safety_penalty, then non-dominant, then lower index
    def sort_key(item):
        score, idx, breakdown, features = item
        in_dominant = False
        for group in groups:
            if idx in group.candidate_indices and group.group_id == trap_decision.dominant_group_id:
                in_dominant = True
                break
        return (-score, features.safety_penalty, 1 if in_dominant else 0, idx)

    scored.sort(key=sort_key)

    # Select winner
    winner_score, winner_idx, winner_breakdown, winner_features = scored[0]
    winner_cid = _build_candidate_id(candidates[winner_idx], winner_idx)

    return DiversitySelectionResult(
        selected_candidate_id=winner_cid,
        selected_candidate_hash=candidates[winner_idx].raw_output_hash,
        selected_index=winner_idx,
        selection_strategy="diversity_v1",
        candidate_count=len(candidates),
        diversity_candidate_count=len(candidates),
        duplicate_group_count=len(groups),
        popularity_trap_detected=trap_decision.detected,
        popularity_trap_reason=trap_decision.reason,
        score_breakdown=[s[2] for s in scored],
        rejected_by_diversity=[],
        fail_closed=False,
        failure_reasons=[],
    )
