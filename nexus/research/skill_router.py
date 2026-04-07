from typing import List, Dict, Any, Optional
from pathlib import Path

class SkillRouter:
    """
    🔀 Research Skill Router (DeepScientist Config Layer)
    職責: 基於當前階段加載對應的行為模型 (SKILL.md)。
    """
    STAGE_MAP = {
        "P": "scout",
        "X": "baseline",
        "D": "idea",
        "R": "experiment",
        "A": "analysis",
        "C": "decision"
    }

    def __init__(self, skills_dir: Optional[Path] = None):
        self.skills_dir = skills_dir or Path("nexus/research/skills")

    def get_skill_path(self, stage_code: str) -> Optional[Path]:
        """獲取階段代碼 (P/X/D/R/A/C) 對應的 SKILL.md 路徑。"""
        folder = self.STAGE_MAP.get(stage_code)
        if not folder:
            return None
        return self.skills_dir / folder / "SKILL.md"

    def load_skill_content(self, stage_code: str) -> str:
        """加載 SKILL.md 的內容。"""
        path = self.get_skill_path(stage_code)
        if not path or not path.exists():
            return f"# Skill Placeholder for {stage_code}\n(No SKILL.md found)"
        
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def get_next_stage(self, current_stage: str, result: Dict[str, Any]) -> str:
        """
        🔮 路由決策邏輯 (待對接 Phase 3 Bayesian 卷積)
        """
        # 預設線性流程
        stages = list(self.STAGE_MAP.keys())
        try:
            idx = stages.index(current_stage)
            if idx + 1 < len(stages):
                return stages[idx + 1]
        except ValueError:
            pass
        return "C" # 最終收斂
