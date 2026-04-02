from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import shutil
import re
import yaml

class SkillCompressor:
    """🌲 Skill Compressor: 碎片技能歸併與原子結晶 (v23 Forest)"""
    
    def __init__(self, skill_root: str = "~/.agents/skills"):
        self.skill_root = Path(os.path.expanduser(skill_root))
        self.crystallized_dir = self.skill_root / "crystallized"
        self.backup_dir = self.skill_root / "backup"

    def compress_all(self):
        """執行全域壓縮流程"""
        if not self.skill_root.exists():
            return "Skill root not found."

        self.crystallized_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)

        # 1. 蒐集 auto-distilled 技能
        skills = list(self.skill_root.glob("auto-distilled.*"))
        if not skills:
            return "No auto-distilled skills found to compress."

        groups: Dict[str, List[Path]] = {}
        for s in skills:
            # 依據名稱前綴分群 (e.g. fix_xxx -> fix)
            name = s.name.replace("auto-distilled.", "")
            prefix = name.split('_')[0] if '_' in name else "general"
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(s)

        # 2. 執行歸併
        for prefix, paths in groups.items():
            self._merge_group(prefix, paths)

        return f"Successfully compressed {len(skills)} skills into {len(groups)} crystallized units."

    def _merge_group(self, prefix: str, paths: List[Path]):
        """將同一組的技能合併為一個 crystallized 檔案"""
        merged_content = f"""---
name: "crystallized_{prefix}"
description: "Crystallized skill group: {prefix}"
---

# 🌲 Crystallized Forest: {prefix}

本單元由多個自動蒸餾技能壓縮而成，代表該領域的原子特化知識。

## 🧬 歸併模式庫
"""
        for p in paths:
            skill_md = p / "SKILL.md"
            if skill_md.exists():
                content = skill_md.read_text()
                # 提取模式部分
                patterns = re.findall(r"- Logic: (.*)", content)
                for pat in patterns:
                    merged_content += f"- {pat} (Source: {p.name})\n"
                
                # 移動到備份區
                shutil.move(str(p), str(self.backup_dir / p.name))

        target_file = self.crystallized_dir / f"{prefix}.md"
        target_file.write_text(merged_content)
