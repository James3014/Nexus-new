from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class FuzzyFunctionSpec:
    name: str
    version: str
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    backend: str  # "deterministic", "tiny_model", "paw", "llm"
    claim_boundary: str


@dataclass(frozen=True)
class FuzzyFunctionResult:
    name: str
    version: str
    score: float
    label: str
    confidence: float
    reasons: list[str]
    backend: str
    deterministic: bool


_registry: dict[str, tuple[FuzzyFunctionSpec, Callable[..., FuzzyFunctionResult]]] = {}


def register(name: str, spec: FuzzyFunctionSpec, impl: Callable[..., FuzzyFunctionResult]) -> None:
    if name in _registry:
        raise ValueError(f"Fuzzy function '{name}' already registered")
    _registry[name] = (spec, impl)


def evaluate(name: str, **inputs: Any) -> FuzzyFunctionResult:
    if name not in _registry:
        raise KeyError(f"Fuzzy function '{name}' not found")

    spec, impl = _registry[name]

    # Validate required keys
    for key in spec.input_schema:
        if key not in inputs:
            raise ValueError(f"Missing required input: {key}")

    return impl(**inputs)


def list_functions() -> list[FuzzyFunctionSpec]:
    return [spec for spec, _ in _registry.values()]


# --- Deterministic backend implementations ---


def _candidate_quality_impl(syntax_like_score: float, safety_penalty: float) -> FuzzyFunctionResult:
    score = max(0.0, min(1.0, syntax_like_score - safety_penalty))
    if score >= 0.6:
        label = "high"
    elif score >= 0.3:
        label = "medium"
    else:
        label = "low"
    return FuzzyFunctionResult(
        name="candidate_quality_v1",
        version="1.0",
        score=score,
        label=label,
        confidence=1.0,
        reasons=[f"syntax_score={syntax_like_score}", f"safety_penalty={safety_penalty}"],
        backend="deterministic",
        deterministic=True,
    )


def _duplicate_similarity_impl(jaccard_similarity: float, same_hash: bool, same_target: bool) -> FuzzyFunctionResult:
    if same_hash:
        score = 1.0
    else:
        score = jaccard_similarity * (0.8 if same_target else 0.5)

    if same_hash:
        label = "exact"
    elif score >= 0.85:
        label = "near"
    else:
        label = "none"

    reasons = [f"jaccard={jaccard_similarity}", f"same_hash={same_hash}", f"same_target={same_target}"]
    return FuzzyFunctionResult(
        name="duplicate_similarity_v1",
        version="1.0",
        score=score,
        label=label,
        confidence=1.0,
        reasons=reasons,
        backend="deterministic",
        deterministic=True,
    )


def _popularity_trap_risk_impl(
    dominant_group_ratio: float,
    has_low_syntax: bool,
    has_safety_penalty: bool,
    model_homogeneous: bool,
) -> FuzzyFunctionResult:
    score = 0.0
    reasons = []

    if dominant_group_ratio > 0.5:
        score += min(0.4, dominant_group_ratio * 0.4)
        reasons.append(f"dominant_ratio={dominant_group_ratio}")
    if has_low_syntax:
        score += 0.2
        reasons.append("has_low_syntax")
    if has_safety_penalty:
        score += 0.2
        reasons.append("has_safety_penalty")
    if model_homogeneous:
        score += 0.2
        reasons.append("model_homogeneous")

    score = min(1.0, score)

    if score >= 0.6:
        label = "high"
    elif score >= 0.3:
        label = "medium"
    else:
        label = "low"

    return FuzzyFunctionResult(
        name="popularity_trap_risk_v1",
        version="1.0",
        score=score,
        label=label,
        confidence=1.0,
        reasons=reasons,
        backend="deterministic",
        deterministic=True,
    )


def _memory_usefulness_impl(used_by_later_stage: bool, outcome: str, age_hours: float) -> FuzzyFunctionResult:
    return FuzzyFunctionResult(
        name="memory_usefulness_v1",
        version="1.0",
        score=0.0,
        label="unknown",
        confidence=0.0,
        reasons=["not_implemented_deterministic"],
        backend="deterministic",
        deterministic=True,
    )


# Register all deterministic backends
register(
    "candidate_quality_v1",
    FuzzyFunctionSpec(
        name="candidate_quality_v1",
        version="1.0",
        input_schema={"syntax_like_score": "float", "safety_penalty": "float"},
        output_schema={"score": "float", "label": "str"},
        backend="deterministic",
        claim_boundary="Score is deterministic based on syntax and safety. Does not assess semantic correctness.",
    ),
    _candidate_quality_impl,
)

register(
    "duplicate_similarity_v1",
    FuzzyFunctionSpec(
        name="duplicate_similarity_v1",
        version="1.0",
        input_schema={"jaccard_similarity": "float", "same_hash": "bool", "same_target": "bool"},
        output_schema={"score": "float", "label": "str"},
        backend="deterministic",
        claim_boundary="Score is deterministic based on token similarity. Does not assess semantic equivalence.",
    ),
    _duplicate_similarity_impl,
)

register(
    "popularity_trap_risk_v1",
    FuzzyFunctionSpec(
        name="popularity_trap_risk_v1",
        version="1.0",
        input_schema={
            "dominant_group_ratio": "float",
            "has_low_syntax": "bool",
            "has_safety_penalty": "bool",
            "model_homogeneous": "bool",
        },
        output_schema={"score": "float", "label": "str"},
        backend="deterministic",
        claim_boundary="Risk score is heuristic-based. Does not predict actual popularity trap occurrence.",
    ),
    _popularity_trap_risk_impl,
)

register(
    "memory_usefulness_v1",
    FuzzyFunctionSpec(
        name="memory_usefulness_v1",
        version="1.0",
        input_schema={"used_by_later_stage": "bool", "outcome": "str", "age_hours": "float"},
        output_schema={"score": "float", "label": "str"},
        backend="deterministic",
        claim_boundary="Placeholder only. No real usefulness assessment implemented.",
    ),
    _memory_usefulness_impl,
)
