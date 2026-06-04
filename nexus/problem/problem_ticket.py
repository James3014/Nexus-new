from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from .taxonomy import ProblemClass, Severity

@dataclass(frozen=True)
class ProblemTicket:
    """
    🎟️ Task M2: Standardized Problem Ticket (Inner Contract)
    職責: 作為控制平面唯一的進線契約。所有外部輸入必須先轉換為此格式。
    Linus Good Taste: 將特殊情況轉化為資料，消滅主流程中的 if/else。
    """
    task_id: str
    problem_class: ProblemClass
    domain_family: str
    severity: Severity
    change_scope: str # e.g., "local", "framework", "global"
    rollback_required: bool
    evidence_inputs: List[str] = field(default_factory=list)
    acceptance_contract: List[str] = field(default_factory=list)
    policy_profile: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)
