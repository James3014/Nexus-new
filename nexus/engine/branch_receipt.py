import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

@dataclass
class MicroSwarmReceipt:
    """
    🛡️ MicroSwarmReceipt: 微蜂群執行收據
    記錄並行探索的所有分支細節，確保治理可追溯性。
    """
    task_id: str
    swarm_triggered: bool
    trigger_reason: str
    branch_count: int
    selected_candidate: Optional[str] = None
    final_gate_verdict: str = "PENDING"
    branches: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MicroSwarmReceipt":
        return cls(**data)
