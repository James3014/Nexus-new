from dataclasses import dataclass
from typing import Optional

@dataclass
class OrchestratorConfig:
    """R1: NexusOrchestrator 執行配置物件。"""
    task: str
    skill_id: str
    mode: str = "developer"
