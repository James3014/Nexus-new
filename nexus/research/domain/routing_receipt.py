from dataclasses import dataclass
from typing import Optional, List

@dataclass(frozen=True)
class RoutingReceipt:
    task_id: str
    selected_route: str
    confidence_score: float
    rationale: str          # 路由理由 (Evidence Chain)
    fallback_route: Optional[str] = None
    manual_override: bool = False
