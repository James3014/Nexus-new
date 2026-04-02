from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

class PhaseHealthSignals(BaseModel):
    """
    Formal schema for Nexus Phase Health Signals (PHA-001)
    """
    # P: Plan
    plan_completeness: float = Field(0.0, ge=0, le=100)
    dependency_validity: float = Field(0.0, ge=0, le=100)
    spec_clarity: float = Field(0.0, ge=0, le=100)

    # X: Research
    evidence_quality: float = Field(0.0, ge=0, le=100)
    source_relevance: float = Field(0.0, ge=0, le=100)
    research_latency_norm: float = Field(0.0, ge=0, le=100) # 越小越好，100-latency 為得分

    # D: Diagnosis
    root_cause_confidence: float = Field(0.0, ge=0, le=100)
    diagnosis_precision: float = Field(0.0, ge=0, le=100)
    false_positive_rate: float = Field(0.0, ge=0, le=100) # 越小越好

    # R: Repair
    fix_success_rate: float = Field(0.0, ge=0, le=100)
    retry_penalty: float = Field(0.0, ge=0, le=100) # 越小越好
    scope_drift: float = Field(0.0, ge=0, le=100) # 越小越好

    # A: Audit
    regression_pass_rate: float = Field(0.0, ge=0, le=100)
    side_effect_score: float = Field(0.0, ge=0, le=100)
    coverage_signal: float = Field(0.0, ge=0, le=100)

    # C: Crystal/Learning
    crystal_reuse_rate: float = Field(0.0, ge=0, le=100)
    lesson_quality: float = Field(0.0, ge=0, le=100)
    next_run_hit_rate: float = Field(0.0, ge=0, le=100)

    metadata: Dict[str, Any] = Field(default_factory=dict)
