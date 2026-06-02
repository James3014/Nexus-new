from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AutonomyObservationReceipt:
    """Phase 6 成本感知自治觀測收據，僅供內部審計與效能分析使用"""
    schema_version: str = "autonomy_observation_receipt.v1"
    task_id: str = ""
    task_class: str = "unknown"  # e.g., algebraic, semantic, auth, env
    route_selected: str = ""
    model_class: str = "mixed"    # e.g., local-7b, local-14b, remote-frontier
    
    # 成本與效能量化
    wall_time_sec: float = 0.0
    retry_count: int = 0
    token_total_estimated: int = 0
    
    # 治理與品質指標
    evidence_complete: bool = False
    governance_clean: bool = True
    stop_layer_matched: bool = True
    syntax_gate_passed: bool = True
    
    # 邊界約束
    promotion_effect: str = "none"
    observation_only: bool = True
    
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AutonomyObserver:
    """負責收集並建構自治觀測數據"""
    
    def capture_observation(self, ctx: Any, task_metadata: dict[str, Any] | None = None) -> AutonomyObservationReceipt:
        task_metadata = task_metadata or {}
        
        # 從 context 中提取量化指標
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
