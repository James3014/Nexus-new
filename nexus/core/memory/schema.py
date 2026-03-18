from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class EpisodicMemory(BaseModel):
    """
    🧠 Episodic Memory Schema
    記錄 Agent 在特定任務中的單次行動片段及其結果。
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "run_id": "run-123",
                "task_id": "task-456",
                "state_before": {"file_exists": False},
                "action": {"type": "write_file", "path": "test.txt"},
                "state_after": {"file_exists": True},
                "reward": 1.0,
                "timestamp": "2024-03-19T10:00:00"
            }
        }
    )

    run_id: str = Field(..., description="唯一的執行 ID")
    task_id: str = Field(default="", description="任務 ID")
    state_before: Dict[str, Any] = Field(default_factory=dict, description="執行前的狀態")
    action: Dict[str, Any] = Field(default_factory=dict, description="執行的行動")
    state_after: Dict[str, Any] = Field(default_factory=dict, description="執行後的狀態")
    reward: float = Field(default=0.0, description="結果的獎勵值")
    timestamp: datetime = Field(default_factory=datetime.now, description="紀錄時間")
