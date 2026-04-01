import os
import re
from pathlib import Path
from datetime import datetime

class SkillDistiller:
    """🧪 [Wave 1] Skill Distiller: Crystallizing wisdom from diffs"""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.output_dir = Path("~/.agents/skills/auto/").expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def distill(self, diff_text: str, lesson: str = "N/A") -> Path:
        # 🚀 行動 3: 從 Diff 提取結晶
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        skill_name = f"skill_{timestamp}.md"
        skill_path = self.output_dir / skill_name
        
        # 匿名化與內容生成
        content = f"""# Nexus Autogen Skill: {timestamp}

## Context 
{lesson}

## Crystallized Diff
```diff
{self._anonymize(diff_text)}
```

## Governance Baseline
- AOS: 155+ (Post-Wave 1)
- Security: [v23 Hardened]
"""
        with open(skill_path, "w") as f:
            f.write(content)
            
        print(f"🧪 [Distiller] New skill crystallized: {skill_path.name}")
        return skill_path

    def _anonymize(self, text: str) -> str:
        # 簡單脫敏：移除路徑與 Key
        text = re.sub(r"/Users/[^/]+", "/root", text)
        text = re.sub(r"sk-[a-zA-Z0-9]{20,}", "sk-REDACTED", text)
        return text
