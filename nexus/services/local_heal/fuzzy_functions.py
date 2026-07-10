from __future__ import annotations

import json
import os
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
        # P5-V3: Match original inline behavior — no multiplier for same_target
        score = jaccard_similarity

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


def _quota_degradation_risk_impl(
    cloud_budget_ratio: float,
    committee_budget_ratio: float,
    candidate_count: int,
) -> FuzzyFunctionResult:
    """EA-R10: Quota degradation risk scoring."""
    score = 0.0
    reasons = []

    if cloud_budget_ratio < 0.2:
        score += 0.4
        reasons.append(f"cloud_low={cloud_budget_ratio:.2f}")
    elif cloud_budget_ratio < 0.5:
        score += 0.2
        reasons.append(f"cloud_constrained={cloud_budget_ratio:.2f}")

    if committee_budget_ratio < 0.2:
        score += 0.3
        reasons.append(f"committee_low={committee_budget_ratio:.2f}")
    elif committee_budget_ratio < 0.5:
        score += 0.15
        reasons.append(f"committee_constrained={committee_budget_ratio:.2f}")

    if candidate_count > 5:
        score += 0.1
        reasons.append(f"high_candidate_count={candidate_count}")

    score = min(1.0, score)

    if score >= 0.6:
        label = "high"
    elif score >= 0.3:
        label = "medium"
    else:
        label = "low"

    return FuzzyFunctionResult(
        name="quota_degradation_risk_v1",
        version="1.0",
        score=score,
        label=label,
        confidence=1.0,
        reasons=reasons,
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

register(
    "quota_degradation_risk_v1",
    FuzzyFunctionSpec(
        name="quota_degradation_risk_v1",
        version="1.0",
        input_schema={
            "cloud_budget_ratio": "float",
            "committee_budget_ratio": "float",
            "candidate_count": "int",
        },
        output_schema={"score": "float", "label": "str"},
        backend="deterministic",
        claim_boundary="Risk score is heuristic-based. Does not predict actual quota degradation.",
    ),
    _quota_degradation_risk_impl,
)


class PawCompiler:
    INTERPRETER_MODEL = "Qwen3-0.6B"

    def __init__(self) -> None:
        self._paw_enabled = os.environ.get("NEXUS_PAW_COMPILE") == "1"
        self._model = None
        self._tokenizer = None

    def is_enabled(self) -> bool:
        return self._paw_enabled

    def compile(self) -> bool:
        if not self._paw_enabled:
            return False
        try:
            self._load_model()
            return self._model is not None
        except Exception:
            return False

    def _load_model(self) -> None:
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self.INTERPRETER_MODEL)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.INTERPRETER_MODEL,
                device_map="auto",
                torch_dtype="auto",
            )
        except Exception:
            self._model = None
            self._tokenizer = None

    def evaluate(self, name: str, **inputs: Any) -> FuzzyFunctionResult:
        if not self._paw_enabled or self._model is None:
            return evaluate(name, **inputs)
        try:
            prompt = json.dumps({"function": name, "inputs": inputs})
            import torch
            device = next(self._model.parameters()).device
            inp = self._tokenizer(prompt, return_tensors="pt").to(device)
            out = self._model.generate(**inp, max_new_tokens=128)
            raw = self._tokenizer.decode(out[0], skip_special_tokens=True)
            result = json.loads(raw)
            return FuzzyFunctionResult(
                name=name,
                version="1.0",
                score=float(result.get("score", 0.0)),
                label=str(result.get("label", "unknown")),
                confidence=float(result.get("confidence", 0.0)),
                reasons=result.get("reasons", ["paw_compiled"]),
                backend="paw",
                deterministic=False,
            )
        except Exception:
            return evaluate(name, **inputs)
