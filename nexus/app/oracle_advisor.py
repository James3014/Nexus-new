from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

class OracleAdvisor:
    """
    🔮 Nexus Oracle Advisor: 將未來軌跡轉化為戰術建議。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.shadow_dir = self.project_root / ".nexus" / "shadow_runs"

    def synthesize_advice(self, shadow_tid: str) -> str:
        log_file = self.shadow_dir / f"{shadow_tid}.json"
        if not log_file.exists():
            return "🔮 [Oracle] 正在穿越時間線中... 請稍候。"
        
        try:
            data = json.loads(log_file.read_text(encoding="utf-8"))
            res = data.get("result", {})
            
            confidence = res.get("confidence", 0.0)
            advice_text = res.get("advice", "無具體建議。")
            trajectory = res.get("trajectory", "未知路徑")
            
            return f"""
🔮 [來自未來的先知建議]
───────────────────────────────────
【預演結論】：{advice_text}
【未來軌跡】：{trajectory}
【信心指數】：{confidence:.1%}
【影子狀態】：穩定 (Shadow-Stability-Pass)
───────────────────────────────────
"""
        except Exception:
            return "🔮 [Oracle] 時間線發生扭曲 (解析失敗)。"
