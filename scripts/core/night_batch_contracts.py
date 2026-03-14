from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

class NexusIssue(BaseModel):
    """單個夜班工單定義"""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str
    goal: str
    priority: int = 1  # 1 (High) to 5 (Low)
    domain: str = "general"  # frontend, backend, infra
    budget_token: int = 5000
    retry_max: int = 3
    allowed_paths: List[str] = ["*"]
    done_criteria: List[str] = []
    metadata: Dict[str, Any] = {}

class NexusBatch(BaseModel):
    """夜班批次任務定義"""
    batch_id: str
    started_at: datetime = Field(default_factory=datetime.now)
    issues: List[NexusIssue] = []
    workers_count: int = 2
    repo_url: Optional[str] = None
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED
    total_token_consumed: int = 0
    metadata: Dict[str, Any] = {}

class BatchLogRecord(BaseModel):
    """批量處理中的單筆 Log 紀錄"""
    timestamp: datetime = Field(default_factory=datetime.now)
    task_id: str
    phase: str  # P, D, X, R, A, C
    status: str
    summary: str
    token_cost: int = 0
