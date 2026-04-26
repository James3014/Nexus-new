from __future__ import annotations
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Optional
from .shadow_bus import ShadowBus

class OracleDispatcher:
    """
    🧠 Nexus Oracle Dispatcher: 意圖感應與影子任務派發。
    將自然語言輸入轉化為背景演化任務。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.bus = ShadowBus(project_root)

    def trigger_shadow_sync(self, user_input: str) -> Optional[str]:
        """
        非阻塞觸發影子執行。
        """
        from nexus.experiments.msa_routing.query_classifier import classify_query
        
        # 使用正式的 MSA 分類器取代原有的樸素對映
        query_type = classify_query(user_input)
        
        # 轉換 MSA query type 到執行 mode
        mode_mapping = {
            "code": "hyper",
            "rule": "swarm",
            "belief": "baseline",
            "artifact": "nightshift", 
            "default": "hyper"
        }
        selected_mode = mode_mapping.get(query_type, "hyper")
        
        # 產生唯一影子任務 ID
        tid = f"shadow_{hashlib.md5(user_input.encode()).hexdigest()[:8]}"
        
        # 派發
        self.bus.spawn_speculative_run(tid, user_input, mode=selected_mode)
        return tid

if __name__ == "__main__":
    dispatcher = OracleDispatcher(Path("."))
    tid = dispatcher.trigger_shadow_sync("refactor the auth service for better speed")
    print(f"Shadow task triggered: {tid}")
