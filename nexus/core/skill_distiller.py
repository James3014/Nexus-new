import os
import re
from typing import List, Dict

class SkillDistiller:
    """🧬 Skill Distiller: 從 Git Diff 自動提煉技術模式 (v23 Eternal)"""
    
    def __init__(self, skill_root: str = "~/.agents/skills"):
        self.skill_root = os.path.expanduser(skill_root)

    def distill_from_diff(self, diff_text: str, name: str) -> str:
        """從差異中提取邏輯並生成 SKILL.md"""
        # 1. 提取關鍵模式 (Regex 模擬)
        patterns = self._extract_patterns(diff_text)
        
        # 2. 生成規格
        skill_content = self._generate_skill_md(name, patterns)
        
        # 3. 儲存
        target_dir = os.path.join(self.skill_root, f"auto-distilled.{name}")
        os.makedirs(target_dir, exist_ok=True)
        path = os.path.join(target_dir, "SKILL.md")
        
        with open(path, "w") as f:
            f.write(skill_content)
            
        return path

    def _extract_patterns(self, diff: str) -> List[str]:
        """簡單提取代碼變動中的邏輯特徵"""
        findings = []
        # 搜尋新增的函數或關鍵邏輯
        for line in diff.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                # 偵測 def 或 class
                match = re.search(r'(def|class)\s+(\w+)', line)
                if match:
                    findings.append(f"Logic: {match.group(2)}")
        return findings if findings else ["General improvement"]

    def _generate_skill_md(self, name: str, patterns: List[str]) -> str:
        """構造符合規格的 SKILL.md"""
        p_list = "\n".join([f"- {p}" for p in patterns])
        return f"""---
name: "{name}"
description: "自動蒸餾技能: {name}"
---

# 🧬 自動蒸餾技能: {name}

- **來源**: Git Diff Analyzer
- **提煉模式**:
{p_list}

## ⚡ v23 進化規範
- 本技能由 Nexus v23 自動提煉。
- 使用時須優先遵守「反偷懶鐵律」。
"""

if __name__ == "__main__":
    distiller = SkillDistiller()
    # 測試
    test_diff = "+def new_optimization_logic():\n+    pass"
    path = distiller.distill_from_diff(test_diff, "test_distill")
    print(f"✅ Skill distilled to: {path}")
