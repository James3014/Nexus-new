from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FuzzyFunctionSpec:
    """PAW-F1: Fuzzy function specification for PAW-compatible registry."""
    function_name: str
    version: str
    natural_language_spec: str
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    deterministic_backend: str
    paw_backend_available: bool = False
    paw_runtime_allowed: bool = False
    calibration_fixture: str = ""
    safety_scope: str = ""
    receipt_fields: list[str] = field(default_factory=list)


# PAW-F1: Initial fuzzy function specs
FUZZY_FUNCTION_SPECS: dict[str, FuzzyFunctionSpec] = {
    "candidate_quality_v1": FuzzyFunctionSpec(
        function_name="candidate_quality_v1",
        version="1.0",
        natural_language_spec="Score candidate quality based on syntax structure and safety. High syntax score with no safety penalties yields high quality. Low syntax or high safety penalty yields low quality.",
        input_schema={"syntax_like_score": "float", "safety_penalty": "float"},
        output_schema={"score": "float", "label": "str"},
        deterministic_backend="candidate_quality_v1",
        calibration_fixture="fuzzy_reward_calibration_v0.json",
        safety_scope="Candidate selection only. Does not affect runtime patch quality.",
        receipt_fields=["quality_score", "quality_label"],
    ),
    "duplicate_similarity_v1": FuzzyFunctionSpec(
        function_name="duplicate_similarity_v1",
        version="1.0",
        natural_language_spec="Measure similarity between two candidate patches using token overlap. Exact hash match yields perfect similarity. High token Jaccard yields near-duplicate.",
        input_schema={"jaccard_similarity": "float", "same_hash": "bool", "same_target": "bool"},
        output_schema={"score": "float", "label": "str"},
        deterministic_backend="duplicate_similarity_v1",
        calibration_fixture="fuzzy_reward_calibration_v0.json",
        safety_scope="Duplicate detection only. Does not affect patch content.",
        receipt_fields=["similarity_score", "similarity_label"],
    ),
    "popularity_trap_risk_v1": FuzzyFunctionSpec(
        function_name="popularity_trap_risk_v1",
        version="1.0",
        natural_language_spec="Assess risk of popularity trap when a dominant duplicate group has low-quality signals. High risk if group is large, has low syntax, safety penalties, or model homogeneity.",
        input_schema={
            "dominant_group_ratio": "float",
            "has_low_syntax": "bool",
            "has_safety_penalty": "bool",
            "model_homogeneous": "bool",
        },
        output_schema={"score": "float", "label": "str"},
        deterministic_backend="popularity_trap_risk_v1",
        calibration_fixture="fuzzy_reward_calibration_v0.json",
        safety_scope="Diversity selection only. Does not affect candidate generation.",
        receipt_fields=["trap_risk_score", "trap_risk_label"],
    ),
    "memory_usefulness_v1": FuzzyFunctionSpec(
        function_name="memory_usefulness_v1",
        version="1.0",
        natural_language_spec="Assess how useful a memory lesson is for current task. Placeholder implementation returns zero score.",
        input_schema={"used_by_later_stage": "bool", "outcome": "str", "age_hours": "float"},
        output_schema={"score": "float", "label": "str"},
        deterministic_backend="memory_usefulness_v1",
        calibration_fixture="fuzzy_reward_calibration_v0.json",
        safety_scope="Memory retrieval only. Does not affect selection or runtime.",
        receipt_fields=["usefulness_score", "usefulness_label"],
    ),
    "quota_degradation_risk_v1": FuzzyFunctionSpec(
        function_name="quota_degradation_risk_v1",
        version="1.0",
        natural_language_spec="Assess risk of quota degradation based on cloud/committee budget ratios and candidate count. High risk if budgets are low and candidate count is high.",
        input_schema={
            "cloud_budget_ratio": "float",
            "committee_budget_ratio": "float",
            "candidate_count": "int",
        },
        output_schema={"score": "float", "label": "str"},
        deterministic_backend="quota_degradation_risk_v1",
        calibration_fixture="fuzzy_reward_calibration_v0.json",
        safety_scope="Quota policy simulation only. Does not affect runtime routing.",
        receipt_fields=["degradation_risk_score", "degradation_risk_label"],
    ),
}


def get_fuzzy_function_spec(name: str) -> FuzzyFunctionSpec | None:
    """Get spec by name."""
    return FUZZY_FUNCTION_SPECS.get(name)


def list_fuzzy_function_specs() -> list[FuzzyFunctionSpec]:
    """List all registered specs."""
    return list(FUZZY_FUNCTION_SPECS.values())
