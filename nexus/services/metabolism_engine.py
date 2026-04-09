import os
import json
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SessionMetabolism:
    """🛡️ Nexus v25.5 Session Metabolism Engine (AutoDream)."""
    def __init__(self, token_limit: int = 128000):
        self.token_limit = token_limit
        self.threshold = 0.85
        self.project_root = Path(__file__).resolve().parents[2]

    def should_distill(self, current_tokens: int) -> bool:
        """🔍 Check if session needs distillation."""
        ratio = current_tokens / self.token_limit
        if ratio >= self.threshold:
            logger.warning(f"⚠️ [Metabolism:REACHED] Token usage {current_tokens} ({ratio:.2%}) triggers distillation.")
            return True
        return False

    def distill(self, session_context: Dict[str, Any]) -> str:
        """📉 語義壓縮：將繁雜的對話提煉為結晶 Seed。"""
        logger.info("🧪 [Metabolism:DISTILLING] Crystallizing session essence...")
        
        # 1. 提取核心精華 (Essence)
        essence = {
            "version": "v23.5-FUSION-BELIEF",
            "last_commit": os.popen("git rev-parse --short HEAD").read().strip(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_objective": session_context.get("goal", "Continuous Evolution"),
            "completed_tasks": session_context.get("done", []),
            "pending_tasks": session_context.get("todo", []),
            "active_beliefs": self._get_active_beliefs(), # 🛡️ 注入長期信念
            "design_specs": self._get_design_specs(),   # 🎨 注入設計靈魂
            "learned_lessons": self._get_recent_lessons()
        }
        
        # 2. 產出物理結晶 Seed 檔案
        seed_path = self.project_root / ".nexus" / "metabolism" / "session_seed.json"
        seed_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(seed_path, 'w', encoding='utf-8') as f:
            json.dump(essence, f, indent=2, ensure_ascii=False)
            
        logger.info(f"💎 [Metabolism:CRYSTAL] Session essence anchored at: {seed_path}")
        
        # 3. 模擬 Arweave 存證
        arweave_tx = f"ar_tx_distilled_{int(datetime.now().timestamp())}"
        return arweave_tx

    def _get_active_beliefs(self) -> list:
        """從 .nexusknowledge/beliefs.jsonl 提取活躍信念"""
        beliefs_path = self.project_root / ".nexusknowledge" / "beliefs.jsonl"
        if not beliefs_path.exists():
            return []
        
        active = []
        try:
            with open(beliefs_path, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    # 僅保留高置信度的活躍信念
                    if data.get("confidence", 0) > 0.9 and data.get("status") != "superseded":
                        active.append({
                            "id": data.get("belief_id") or data.get("id"),
                            "content": data.get("content")
                        })
        except Exception as e:
            logger.error(f"Error reading beliefs for distillation: {e}")
            
        return active[-5:] # 僅帶走最重要的前 5 條

    def _get_design_specs(self) -> dict:
        """從 DESIGN.md 提取核心設計規範"""
        design_path = self.project_root / "nexus_wiki_vault" / "99_Schema" / "DESIGN.md"
        if not design_path.exists():
            return {}
        
        # 簡單提取氛圍與禁忌 (模擬)
        return {
            "atmosphere": "Hardened Industrial, Terminal-First",
            "critical_donts": ["No rounded corners", "No gradients"],
            "critical_dos": ["Must provide physical evidence", "High information density"]
        }

    def _get_recent_lessons(self) -> list:
        """從 .codex_lessons.md 讀取最後三條教訓"""
        lessons_path = self.project_root / ".codex_lessons.md"
        if not lessons_path.exists():
            return []
        content = lessons_path.read_text()
        # 簡單分割模擬
        return content.split("###")[-3:]

# Global Metabolism Service
metabolism = SessionMetabolism()
