from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class HealthMetrics(BaseModel):
    test_pass_rate: float = 0.0 # 0.0 - 1.0
    drift_index: float = 0.0    # 偏離指數 (越小越健康)
    error_rate: float = 0.0     # 錯誤率
    token_efficiency: float = 1.0 # 1.0 為標準
    outcome_quality: float = 1.0 # 成果品質 (0.0 - 1.0)
    last_check_at: Optional[datetime] = None
    status: str = "UNKNOWN"     # HEALTHY, WARNING, CRITICAL

class PhaseMetric(BaseModel):
    health: float = 0.0
    signals: Dict[str, Any] = Field(default_factory=dict)

class TokenAccounting(BaseModel):
    """Token 使用量追蹤"""
    total_usage: int = 0
    raw_model: int = 0
    fallback_est: int = 0
    system_overhead: int = 0
    capture_status: str = "unknown"
    phase_tokens: Dict[str, int] = Field(default_factory=dict)

class ObservabilityContext(BaseModel):
    """追蹤與可觀測性"""
    trace_id: str = ""
    span_id: str = ""
    auto_actions: List[Dict[str, Any]] = Field(default_factory=list)

class AuditCounters(BaseModel):
    """審計與重試計數器"""
    audit_pass_count: int = 0
    retry_count: int = 0
    turn_count: int = 0
    clarification_count: int = 0
    correction_count: int = 0
    unresolved_count: int = 0

class PhaseHealthSnapshot(BaseModel):
    """階段健康快照"""
    health_score: float = 100.0
    health_metrics: HealthMetrics = Field(default_factory=HealthMetrics)
    pipeline_health: float = 100.0
    learning_velocity: float = 0.0
    phase_metrics: Dict[str, PhaseMetric] = Field(
        default_factory=lambda: {
            "P": PhaseMetric(),
            "X": PhaseMetric(),
            "D": PhaseMetric(),
            "R": PhaseMetric(),
            "A": PhaseMetric(),
            "C": PhaseMetric()
        }
    )
