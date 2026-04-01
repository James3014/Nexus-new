import json
from pathlib import Path
from typing import List, Dict, Any

class CrystallizePhase:
    """💎 Nexus L6.1 結晶化階段 (C-Phase)
    
    負責將執行紀錄轉化為高品質工程日誌，並嵌入 Impeccable 標籤。
    對照 .nexus-soul.md 標準：Precise Engineering Labels.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def generate_impeccable_log(self, entries: List[Dict[str, Any]]) -> str:
        """產生帶有工程標籤的精確日誌"""
        log = "# 🗒️ Nexus Daily Engineering Log (L6.1 Impeccable)\n\n"
        for entry in entries:
            # 💡 導入 Impeccable 工程標籤風格
            label = entry.get("type", "feat(core)")
            gate = entry.get("aesthetic_gate", "[]")
            desc = entry.get("desc", entry.get("action", ""))
            
            log += f"- **{label}**: {gate} {desc}\n"
            if "verification" in entry:
                log += f"  - `[Verified]` {entry['verification']}\n"
        
        return log

    def finalize_session(self, session_id: str, entries: List[Dict[str, Any]]):
        """封存 Session 並產出實體證物"""
        log_content = self.generate_impeccable_log(entries)
        log_path = self.project_root / "Daily_Log.md" # 物理對應日誌
        
        with open(log_path, "a") as f:
            f.write(f"\n--- SESSION: {session_id} ---\n")
            f.write(log_content)
            
        print(f"✅ [Crystallize] Daily_Log.md hardened with Impeccable tags. 🟢")
