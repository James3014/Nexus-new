from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SuitabilityVerdict:
    """單一任務類別的適配判定"""
    task_class: str
    small_model_recommended: bool
    observation_only: bool = True
    confidence_score: float = 0.0
    wall_ratio_estimate: float = 1.0
    trust_mismatch_risk: str = "medium"

@dataclass(frozen=True)
class LocalModelSuitabilityMatrix:
    """Phase 6 本地模型適配矩陣，定義自治邊界"""
    schema_version: str = "local_model_suitability_matrix.v1"
    verdicts: dict[str, SuitabilityVerdict] = field(default_factory=dict)
    promotion_allowed: bool = False
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "verdicts": {k: asdict(v) for k, v in self.verdicts.items()},
            "promotion_allowed": self.promotion_allowed
        }

@dataclass(frozen=True)
class AutonomyObservationReceipt:
    """Phase 6 成本感知自治觀測收據，僅供內部審計與效能分析使用"""
    schema_version: str = "autonomy_observation_receipt.v1"
    task_id: str = ""
    task_class: str = "unknown"
    route_selected: str = ""
    model_class: str = "mixed"
    wall_time_sec: float = 0.0
    retry_count: int = 0
    token_total_estimated: int = 0
    evidence_complete: bool = False
    governance_clean: bool = True
    stop_layer_matched: bool = True
    syntax_gate_passed: bool = True
    promotion_effect: str = "none"
    observation_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SuitabilityAssessor:
    """根據觀測數據產出適配判定"""
    
    def assess_suitability(self, observations: list[AutonomyObservationReceipt]) -> LocalModelSuitabilityMatrix:
        class_stats = {}
        for obs in observations:
            cls = obs.task_class
            if cls not in class_stats:
                class_stats[cls] = {"count": 0, "matched": 0, "syntax_ok": 0}
            stats = class_stats[cls]
            stats["count"] += 1
            if obs.stop_layer_matched: stats["matched"] += 1
            if obs.syntax_gate_passed: stats["syntax_ok"] += 1

        verdicts = {}
        for cls, stats in class_stats.items():
            success_rate = stats["matched"] / stats["count"]
            recommended = success_rate > 0.8 and (stats["syntax_ok"] / stats["count"]) > 0.9
            verdicts[cls] = SuitabilityVerdict(
                task_class=cls,
                small_model_recommended=recommended,
                confidence_score=success_rate,
                trust_mismatch_risk="low" if recommended else "high"
            )

        return LocalModelSuitabilityMatrix(verdicts=verdicts)


class AutonomyObserver:
    """負責收集並建構自治觀測數據"""
    
    def capture_observation(self, ctx: Any, task_metadata: dict[str, Any] | None = None) -> AutonomyObservationReceipt:
        task_metadata = task_metadata or {}
        op = getattr(ctx, "op", ctx)
        gov = getattr(ctx, "gov", None)
        
        return AutonomyObservationReceipt(
            task_id=getattr(op, "instance_id", ""),
            task_class=task_metadata.get("task_class", "unknown"),
            route_selected=getattr(op, "recommended_flow", ""),
            model_class=task_metadata.get("model_class", "mixed"),
            wall_time_sec=float(getattr(op, "wall_time_sec", 0.0)),
            retry_count=int(getattr(op, "attempt", 0)),
            token_total_estimated=int(getattr(op, "token_total_estimated", 0)),
            evidence_complete=bool(getattr(op, "final_patch", False) or getattr(op, "reproduced", False)),
            governance_clean=bool(not getattr(op, "failure_reason", "")),
            stop_layer_matched=bool(getattr(gov, "stop_layer_matched", True) if gov else True),
            syntax_gate_passed=bool(getattr(op, "syntax_gate_passed", True)),
            metadata=getattr(op, "model_decisions", []) if hasattr(op, "model_decisions") else {}
        )
