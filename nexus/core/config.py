from dataclasses import dataclass
from typing import Optional

@dataclass
class OrchestratorConfig:
    """R1: NexusOrchestrator 執行配置物件。"""
    task: str
    skill_id: str
    mode: str = "developer"
    
    # 🧬 Feature Flags (v22 Controlled Launch)
    # 所有新功能預設為 OFF (Sir 的指令)
    NEXUS_SHELL_ADAPTER_ENABLED: bool = False
    NEXUS_FS_WATCHER_ENABLED: bool = False
