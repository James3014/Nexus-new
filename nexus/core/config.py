import os
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class OrchestratorConfig:
    """R1: NexusOrchestrator 執行配置物件。"""
    task: str
    skill_id: str
    mode: str = "developer"
    
    # 🧬 Feature Flags (v22 Controlled Launch)
    NEXUS_SHELL_ADAPTER_ENABLED: bool = False
    NEXUS_FS_WATCHER_ENABLED: bool = False

class NexusGlobalConfig:
    """🌍 Nexus 全域配置集散地 (SSoT)"""
    
    # 智慧層 (Ollama)
    OLLAMA_ENDPOINT = os.environ.get("NEXUS_OLLAMA_ENDPOINT", "http://localhost:11434")
    OLLAMA_EMBED_MODEL = os.environ.get("NEXUS_EMBED_MODEL", "nomic-embed-text")
    
    # 通信層 (SSE)
    SSE_PORT = int(os.environ.get("NEXUS_SSE_PORT", "8080"))
    
    # 性能層
    STATE_PRUNE_BYTES = int(os.environ.get("NEXUS_STATE_PRUNE_LIMIT", str(10 * 1024 * 1024))) # 10MB
    MAX_STATE_HISTORY = 100 # 最多保留 100 條狀態紀錄
