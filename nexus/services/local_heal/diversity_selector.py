from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from nexus.services.local_heal.local_cascade_orchestrator import LocalCascadeReceipt
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.fuzzy_functions import evaluate as fuzzy_evaluate


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
    trace_events: list[dict[str, Any]] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    cascade_aware: bool = False
    diversity_aware: bool = True


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


def _compute_syntax_score(patch: str) -> float:
    """P5-V1: More granular syntax-like scoring."""
    if not patch.strip():
        return 0.0
    if len(patch.strip()) < 20:
        return 0.2
    if any(m in patch for m in ["--- ", "+++ ", "@@ "]):
        return 1.0
    if "<<<<<<<" in patch or "=======" in patch:
        return 0.9
    tokens = re.findall(r'\S+', patch)
    code_like = sum(1 for t in tokens if any(c.isalpha() for c in t))
    non_code = len(tokens) - code_like
    if code_like > non_code:
        return 0.6
    return 0.1


def extract_features(candidate: CanonicalPatchCandidate, model: str = "") -> CandidateFeatures:
    """P5-I2/V1: Extract interpretable features from a CanonicalPatchCandidate.

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

    # target_file_match: does the patch actually reference the target file?
    target_file_match = bool(
        candidate.target_file.strip()
        and candidate.normalized_patch
        and candidate.target_file.strip() in candidate.normalized_patch
    )

    # syntax_like_score via granular scorer
    syntax_like_score = _compute_syntax_score(patch)

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

            # P5-V3: Near duplicate via fuzzy function
            if fi.token_set and fj.token_set:
                sim = _jaccard_similarity(fi.token_set, fj.token_set)
                same_target = bool(fi.target_file and fj.target_file and fi.target_file == fj.target_file)
                sim_result = fuzzy_evaluate(
                    "duplicate_similarity_v1",
                    jaccard_similarity=sim,
                    same_hash=(fi.candidate_hash == fj.candidate_hash),
                    same_target=same_target,
                )
                if sim_result.score >= 0.85:
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

    # P5-V3: Use fuzzy function for trap risk
    dominant_features = [features[idx] for idx in dominant.candidate_indices if idx < len(features)]
    has_low_syntax = any(f.syntax_like_score < 0.5 for f in dominant_features)
    has_safety_penalty = any(f.safety_penalty > 0 for f in dominant_features)

    # Model homogeneity check
    models = set()
    for idx in dominant.candidate_indices:
        if idx < len(features):
            models.add(features[idx].source_model)
    model_homogeneous = len(models) == 1 and dominant_size > candidate_count / 2 and any(models)

    risk_result = fuzzy_evaluate(
        "popularity_trap_risk_v1",
        dominant_group_ratio=dominant_size / candidate_count,
        has_low_syntax=has_low_syntax,
        has_safety_penalty=has_safety_penalty,
        model_homogeneous=model_homogeneous,
    )

    trap_reasons = []
    if risk_result.score > 0:
        trap_reasons.extend(risk_result.reasons)

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
    """P5-I5/V3: Score a single candidate for diversity-aware selection.

    Returns (final_score, breakdown_dict).
    """
    # P5-V3: Use fuzzy function for quality scoring
    quality_result = fuzzy_evaluate(
        "candidate_quality_v1",
        syntax_like_score=features.syntax_like_score,
        safety_penalty=features.safety_penalty,
    )
    quality_score = quality_result.score

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
        "fuzzy_function": {
            "name": "candidate_quality_v1",
            "version": "1.0",
            "backend": "deterministic",
            "label": quality_result.label,
        },
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

    # P5-V2: Create trace for selection decisions
    from nexus.services.local_heal.selection_trace import SelectionTrace, SelectionTraceEvent
    trace = SelectionTrace(trace_id="p5-selection", task_id="p5-selection")

    # Extract features for all candidates
    all_features = [extract_features(c, source_models[i]) for i, c in enumerate(candidates)]

    # P5-V2: Trace feature extraction
    for i, f in enumerate(all_features):
        trace.append_event(SelectionTraceEvent(
            event_id="",
            parent_event_id=None,
            phase="feature_extraction",
            event_type="candidate_feature_extracted",
            candidate_index=i,
            candidate_hash=candidates[i].raw_output_hash,
            inputs={"patch_length": f.patch_length, "line_count": f.line_count, "syntax_score": f.syntax_like_score, "safety_penalty": f.safety_penalty},
            outputs={"target_file_match": f.target_file_match},
            decision="scored",
            reason=f"syntax={f.syntax_like_score}, safety={f.safety_penalty}",
            reversible=False,
        ))

    # Group near-duplicates
    groups = group_near_duplicates(all_features)

    # P5-V2: Trace duplicate detection
    trace.append_event(SelectionTraceEvent(
        event_id="",
        parent_event_id=None,
        phase="duplicate_detection",
        event_type="candidate_duplicate_grouped",
        candidate_index=None,
        candidate_hash=None,
        inputs={"group_count": len(groups)},
        outputs={"groups": [{"group_id": g.group_id, "indices": list(g.candidate_indices), "kind": g.duplicate_kind} for g in groups]},
        decision="grouped",
        reason=f"{len(groups)} duplicate groups found",
        reversible=False,
    ))

    # Detect popularity trap
    trap_decision = detect_popularity_trap(all_features, groups)

    # P5-V2: Trace popularity trap
    trace.append_event(SelectionTraceEvent(
        event_id="",
        parent_event_id=None,
        phase="popularity_trap",
        event_type="popularity_trap_detected",
        candidate_index=None,
        candidate_hash=None,
        inputs={"dominant_group_id": trap_decision.dominant_group_id, "dominant_group_size": trap_decision.dominant_group_size},
        outputs={"detected": trap_decision.detected, "action": trap_decision.recommended_action, "reason": trap_decision.reason},
        decision="trap_detected" if trap_decision.detected else "noop",
        reason=trap_decision.reason,
        reversible=False,
    ))

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
        # P5-V2: Trace fail_closed
        trace.append_event(SelectionTraceEvent(
            event_id="",
            parent_event_id=None,
            phase="selection",
            event_type="selection_fail_closed",
            candidate_index=None,
            candidate_hash=None,
            inputs={},
            outputs={"failure_reasons": ["all_candidates_unsafe"]},
            decision="fail_closed",
            reason="all candidates unsafe",
            reversible=False,
        ))
        trace.freeze()
        trace_events = trace.to_receipt_fragment().get("p5_trace_events", [])

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
            trace_events=trace_events,
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

    # P5-V2: Trace winner selection
    trace.append_event(SelectionTraceEvent(
        event_id="",
        parent_event_id=None,
        phase="scoring",
        event_type="candidate_scored",
        candidate_index=winner_idx,
        candidate_hash=candidates[winner_idx].raw_output_hash,
        inputs={"winner_index": winner_idx},
        outputs={"final_scores": {str(s[1]): s[0] for s in scored}},
        decision="selected",
        reason=f"winner=candidate[{winner_idx}], score={winner_score}",
        reversible=False,
    ))

    trace.freeze()
    trace_events = trace.to_receipt_fragment().get("p5_trace_events", [])

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
        trace_events=trace_events,
    )


def select_from_cascade(
    cascade_receipt: LocalCascadeReceipt,
    all_stage_candidates: list[CanonicalPatchCandidate],
) -> DiversitySelectionResult:
    if not all_stage_candidates:
        return DiversitySelectionResult(
            selected_candidate_id="",
            selected_candidate_hash=cascade_receipt.winner_candidate_hash,
            selected_index=-1,
            selection_strategy="cascade_aware",
            candidate_count=0,
            diversity_candidate_count=0,
            duplicate_group_count=0,
            popularity_trap_detected=False,
            popularity_trap_reason="",
            score_breakdown=[],
            rejected_by_diversity=[],
            fail_closed=False,
            failure_reasons=[],
            cascade_aware=True,
        )

    if len(all_stage_candidates) == 1:
        c = all_stage_candidates[0]
        cid = _build_candidate_id(c, 0)
        return DiversitySelectionResult(
            selected_candidate_id=cid,
            selected_candidate_hash=c.raw_output_hash,
            selected_index=0,
            selection_strategy="cascade_aware_single",
            candidate_count=1,
            diversity_candidate_count=1,
            duplicate_group_count=0,
            popularity_trap_detected=False,
            popularity_trap_reason="",
            score_breakdown=[{"candidate_id": cid, "index": 0, "strategy": "cascade_aware_single"}],
            rejected_by_diversity=[],
            fail_closed=False,
            failure_reasons=[],
            cascade_aware=True,
        )

    base = select_diverse_candidate(all_stage_candidates)
    return DiversitySelectionResult(
        selected_candidate_id=base.selected_candidate_id,
        selected_candidate_hash=base.selected_candidate_hash,
        selected_index=base.selected_index,
        selection_strategy="cascade_aware_diversity",
        candidate_count=base.candidate_count,
        diversity_candidate_count=base.diversity_candidate_count,
        duplicate_group_count=base.duplicate_group_count,
        popularity_trap_detected=base.popularity_trap_detected,
        popularity_trap_reason=base.popularity_trap_reason,
        score_breakdown=base.score_breakdown,
        rejected_by_diversity=base.rejected_by_diversity,
        fail_closed=base.fail_closed,
        failure_reasons=base.failure_reasons,
        trace_events=base.trace_events,
        cascade_aware=True,
        diversity_aware=base.diversity_aware,
    )


@dataclass(frozen=True)
class PopularityTrapResult:
    trapped_candidate_ids: tuple[str, ...]
    similarity_scores: dict[str, float]


def _compute_pairwise_jaccard(texts: list[str]) -> list[list[float]]:
    token_sets = [frozenset(re.findall(r'\S+', t)) for t in texts]
    n = len(token_sets)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            matrix[i][j] = _jaccard_similarity(token_sets[i], token_sets[j])
    return matrix


def _build_score_map(score_breakdown: list[dict[str, Any]]) -> dict[int, float]:
    """Build index→final_score lookup from score_breakdown (which may be sorted differently)."""
    out: dict[int, float] = {}
    for entry in score_breakdown:
        idx = entry.get("index")
        if idx is not None:
            out[idx] = entry.get("final_score", float("-inf"))
    return out


def select_with_diversity(
    candidates: list[CanonicalPatchCandidate],
    similarity_threshold: float = 0.85,
) -> DiversitySelectionResult:
    base = select_diverse_candidate(candidates)

    if len(candidates) <= 1:
        return DiversitySelectionResult(
            selected_candidate_id=base.selected_candidate_id,
            selected_candidate_hash=base.selected_candidate_hash,
            selected_index=base.selected_index,
            selection_strategy="diversity_aware",
            candidate_count=base.candidate_count,
            diversity_candidate_count=base.diversity_candidate_count,
            duplicate_group_count=base.duplicate_group_count,
            popularity_trap_detected=False,
            popularity_trap_reason="",
            score_breakdown=base.score_breakdown,
            rejected_by_diversity=base.rejected_by_diversity,
            fail_closed=base.fail_closed,
            failure_reasons=base.failure_reasons,
            trace_events=base.trace_events,
            cascade_aware=base.cascade_aware,
            diversity_aware=True,
        )

    raw_texts = [c.raw_output for c in candidates]
    sim_matrix = _compute_pairwise_jaccard(raw_texts)
    n = len(candidates)

    # Cluster: group indices where pairwise sim > threshold
    clusters: list[set[int]] = []
    assigned: set[int] = set()
    for i in range(n):
        if i in assigned:
            continue
        cluster = {i}
        for j in range(i + 1, n):
            if j in assigned:
                continue
            if sim_matrix[i][j] > similarity_threshold:
                cluster.add(j)
        for idx in cluster:
            assigned.add(idx)
        clusters.append(cluster)

    # Largest cluster determines popularity trap
    largest = max(clusters, key=len) if clusters else set()
    majority = len(largest) > n // 2

    trapped_indices = sorted(largest) if majority else []
    non_trapped = [i for i in range(n) if i not in trapped_indices]
    trapped_candidate_ids = [candidates[i].raw_output_hash[:16] for i in trapped_indices]

    score_map = _build_score_map(base.score_breakdown)

    if non_trapped and majority:
        best_idx = max(non_trapped, key=lambda i: score_map.get(i, float("-inf")))
    else:
        best_idx = base.selected_index

    cid = candidates[best_idx].raw_output_hash[:16] + f"#{best_idx}"
    return DiversitySelectionResult(
        selected_candidate_id=cid,
        selected_candidate_hash=candidates[best_idx].raw_output_hash,
        selected_index=best_idx,
        selection_strategy="diversity_aware",
        candidate_count=n,
        diversity_candidate_count=n,
        duplicate_group_count=base.duplicate_group_count,
        popularity_trap_detected=majority,
        popularity_trap_reason="popularity_trap" if majority else "",
        score_breakdown=base.score_breakdown,
        rejected_by_diversity=list(trapped_candidate_ids),
        fail_closed=base.fail_closed,
        failure_reasons=base.failure_reasons,
        trace_events=base.trace_events,
        cascade_aware=base.cascade_aware,
        diversity_aware=True,
    )
