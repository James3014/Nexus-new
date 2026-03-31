from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

@dataclass
class SkillSuccessMetric:
    repair_success: bool = False
    retry_count: int = 0
    pattern_reuse_rate: float = 0.0
    entrypoint: str = ""
    success_rate: float = 0.0
    
    # 🆕 Decay Tracking
    last_used_at: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]

@dataclass
class SkillFrontmatter:
    name: str
    description: str
    task_id: str
    success_metric: SkillSuccessMetric
    source: str = "nexus-auto-crystal"
    trust_level: str = "auto-generated"
    task_type: str = "unknown"
    keywords: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    
    # --- 全六階段學習信號 ---
    plan_strategy: str = ""
    winning_hypothesis: str = ""
    phantom_patterns: List[str] = field(default_factory=list)
    version: str = "1.0"
    cycle_count: int = 0
    cycle_root_cause: str = ""
    embedding_model_version: str = ""
    last_used_at: str = ""
    
    # 🧬 進化基因：調度模式與上下文指紋
    orchestration_pattern: str = ""
    context_fingerprint: str = ""
    
    # --- VDD：驗證驅動信號 ---
    verification_commands: List[str] = field(default_factory=list)
    verification_exit_codes: List[int] = field(default_factory=list)

    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillFrontmatter":
        metric_data = data.get("success_metric", {})
        metric = SkillSuccessMetric(**metric_data)
        
        # Filter out success_metric and init separately
        init_data = {k: v for k, v in data.items() if k != "success_metric"}
        return cls(success_metric=metric, **init_data)
