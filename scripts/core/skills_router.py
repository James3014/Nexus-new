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
            "P": "writing-plans",        # Plan 階段使用 v5 寫計畫能力
            "D": "systematic-debugging" # Diag 階段使用核心診斷能力
        }

    def route(self, phase: str, context: Dict[str, Any]) -> str:
        """根據階段與上下文決定使用的 Skill 並返回路徑。"""
        skill_id = self.skill_map.get(phase, "generalist")
        skill_path = self.skills_root / skill_id / "SKILL.md"
        print(f"🎯 [Router] Routing phase {phase} to skill: {skill_id} ({skill_path})")
        return str(skill_path)

if __name__ == "__main__":
    router = SkillsRouter()
    print(f"Test Route P -> {router.route('P', {})}")
