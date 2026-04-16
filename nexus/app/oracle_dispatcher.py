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
        self.intent_map = {
            "refactor": "nightshift",
            "fix": "hyper",
            "implement": "hyper",
            "add": "swarm",
            "check": "baseline"
        }

    def trigger_shadow_sync(self, user_input: str) -> Optional[str]:
        """
        非阻塞觸發影子執行。
        """
        user_input_l = user_input.lower()
        
        # 簡單意圖識別邏輯 (未來可對接更強的分類器)
        selected_mode = "hyper" # Default
        for key, mode in self.intent_map.items():
            if key in user_input_l:
                selected_mode = mode
                break
        
        # 產生唯一影子任務 ID
        tid = f"shadow_{hashlib.md5(user_input.encode()).hexdigest()[:8]}"
        
        # 派發
        self.bus.spawn_speculative_run(tid, user_input, mode=selected_mode)
        return tid

if __name__ == "__main__":
    dispatcher = OracleDispatcher(Path("."))
    tid = dispatcher.trigger_shadow_sync("refactor the auth service for better speed")
    print(f"Shadow task triggered: {tid}")
