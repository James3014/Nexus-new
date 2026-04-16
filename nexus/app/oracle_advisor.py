from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

class OracleAdvisor:
    """
    🔮 Nexus Oracle Advisor v2: 支援維度感應與「絲滑補全」顯示。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.shadow_dir = self.project_root / ".nexus" / "shadow_runs"

    def synthesize_advice(self, shadow_tid: str, intake_data: Dict[str, Any]) -> str:
        log_file = self.shadow_dir / f"{shadow_tid}.json"
        
        # 準備維度列表顯示
        dims = intake_data.get("found_dimensions", {})
        missing = intake_data.get("missing_dimensions", [])
        
        dim_summary = "\n".join([f"  - {k}: {v} ✅" for k, v in dims.items()])
        if missing:
            dim_summary += "\n" + "\n".join([f"  - {m}: [待定] ❓" for m in missing])

        base_advice = ""
        if log_file.exists():
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                res = data.get("result", {})
                base_advice = f"""
【預演結論】：{res.get('advice', '計算中...')}
【未來軌跡】：{res.get('trajectory', '未知路徑')}
【信心指數】：{res.get('confidence', 0.0):.1%}
【執行指令】：uv run scripts/engine/nexus_cli.py nexus oracle:apply {shadow_tid}
"""
            except: pass
        else:
            base_advice = "\n【影子狀態】：正在背景預演中，您可以隨時套用。"

        return f"""
🔮 [來自未來的主動領航建議]
───────────────────────────────────
【規格猜測 (Speculative Dimensions)】:
{dim_summary}

{base_advice}
【領航狀態】：絲滑對接 (Silk-Intake-Active)
───────────────────────────────────
"""
