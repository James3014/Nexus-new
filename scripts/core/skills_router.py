from pathlib import Path
from typing import Dict, Any


class SkillsRouter:
    """
    🔀 Nexus v5 Skills Router (Simplified Pilot)
    負責將 P-D-X-R-A-C 階段映射至具體的 v5 Skills。
    """

    def __init__(self, skills_root: str = "~/.agents/skills"):
        self.skills_root = Path(skills_root).expanduser()
        self.skill_map = {
            "P": "writing-plans",  # Plan 階段使用 v5 寫計畫能力
            "D": "systematic-debugging",  # Diag 階段使用核心診斷能力
        }

    def route(self, phase: str, context: Dict[str, Any]) -> str:
        """根據階段與上下文決定使用的 Skill 並返回路徑，同時執行模型感知升級。"""
        # 1. 執行 Scorecard 模型感知 (Phase 1 核心)
        score = 0

        # 規則 A: 檔案複雜度
        files_count = len(context.get("files", []))
        if files_count > 5:
            score += 3

        # 規則 B: Linter 嚴重度
        linter_errors = len(context.get("linter_results", []))
        if linter_errors > 3:
            score += 2

        # 規則 C: 歷史深度 (難度累積)
        steps_history_len = len(context.get("steps_history", []))
        if steps_history_len > 2:
            score += 4

        # 規則 D: 任務類別 (重構)
        is_refactoring = any(
            kw in context.get("task_id", "").lower()
            for kw in ["refactor", "migration", "nexus-v5"]
        )
        if is_refactoring:
            score += 5

        # 2. 判斷是否需要提升模型 (Elevation)
        prefer_strong_model = score > 7
        if prefer_strong_model:
            print(f"🚀 [ELEVATED] Total score={score} >7 → prefer_strong_model: Sonnet")

        # 3. 執行路由映射
        skill_id = self.skill_map.get(phase, "generalist")
        skill_path = self.skills_root / skill_id / "SKILL.md"
        print(f"🎯 [Router] Routing phase {phase} to skill: {skill_id} ({skill_path})")

        return str(skill_path)


if __name__ == "__main__":
    router = SkillsRouter()
    print(f"Test Route P -> {router.route('P', {})}")
