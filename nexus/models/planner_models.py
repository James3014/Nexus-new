from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class PlannerResult(BaseModel):
    intent_pass: bool
    best_node: str = "LOCAL_HARDENED"
    handoff_readiness: float = 100.0
    risk_score: float = 0.0
    risks: List[str] = Field(default_factory=list)
    risk_level: str = "LOW"
    tokens_used: int = 0
    refusal_reason: Optional[str] = None

class ImplementationPackSchema(BaseModel):
    task_id: str
    tenant_id: str = "default"
    goal: str
    task_type: str = "fullstack"
    deliverables: List[str] = Field(default_factory=list)
    files_to_modify: List[str] = Field(default_factory=list)
    files_to_create: List[str] = Field(default_factory=list)
    data_models: List[Dict[str, Any]] = Field(default_factory=list)
    ui_blocks: List[str] = Field(default_factory=list)
    commands_to_wire: List[str] = Field(default_factory=list)
    edge_cases: List[str] = Field(default_factory=list)
    acceptance_targets: List[str] = Field(default_factory=list)
    error_handling: List[str] = Field(default_factory=lambda: ["Standard Fallback"])
    out_of_scope: List[str] = Field(default_factory=lambda: ["Any unrelated code modification"])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    wisdom_boosted: bool = False
    source_wisdom: Optional[str] = None
