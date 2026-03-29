from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

@dataclass
class SkillSuccessMetric:
    repair_success: bool = False
    retry_count: int = 0
    pattern_reuse_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

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
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillFrontmatter":
        metric_data = data.get("success_metric", {})
        metric = SkillSuccessMetric(**metric_data)
        
        # Filter out success_metric and init separately
        init_data = {k: v for k, v in data.items() if k != "success_metric"}
        return cls(success_metric=metric, **init_data)
