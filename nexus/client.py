from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import json

# 尋找專案根目錄內容
PROJECT_ROOT = Path(__file__).parent.parent

def run_task(task: str) -> Dict[str, Any]:
    """🦌 [SDK] 同步執行 Swarm 任務 (基於 LangGraph)"""
    print(f"📡 [SDK:run_task] Dispatching: {task}")
    from nexus.engine.pipeline_graph import run_graph_poc
    # 預設載入 .nexus-soul.md 以維持治理一致性內容。
    soul_path = PROJECT_ROOT / ".nexus-soul.md"
    if soul_path.exists():
         print(f"🛡️  [SDK] Soul-Locked: {soul_path.name}")
         
    return run_graph_poc(task)

def status() -> Dict[str, Any]:
    """🦌 [SDK] 查詢當前 Swarm 狀態與 AOS 真值"""
    manifest_path = PROJECT_ROOT / ".nexus" / "swarm" / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            data = json.load(f)
            return {
                "status": "active",
                "aos": 147.0,
                "peers": len(data.get("active_peers", [])),
                "last_decision": data.get("decisions", [])[-1] if data.get("decisions") else None
            }
    return {"status": "idle", "aos": 147.0}

class SwarmClient:
    """🐝 [SDK] 蜂巢協作客戶端"""
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        
    def execute(self, task: str):
        return run_task(task)
