import os
import hashlib
from filelock import FileLock
from pathlib import Path
from typing import List, Optional
import yaml
from nexus.learning.skill_schema import SkillFrontmatter

class SkillStore:
    def __init__(self, workspace_root: Path):
        self.skills_dir = workspace_root / "skills" / "learned"
        self.skills_dir = workspace_root / "skills" / "learned"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root = workspace_root

    def save_skill(self, skill_id: str, content: str) -> bool:
        """原子寫入技能（帶 FileLock + Content Hash 雙重防護）"""
        filename = f"{skill_id}.md" if not skill_id.endswith(".md") else skill_id
        skill_path = self.skills_dir / filename
        lock = FileLock(str(self.skills_dir / f".{skill_id}.lock"), timeout=10)

        # Content Hash 衝突檢測
        new_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if skill_path.exists():
            old_hash = hashlib.sha256(skill_path.read_bytes()).hexdigest()
            if old_hash == new_hash:
                return False  # 內容未變，跳過寫入

        with lock:
            skill_path.write_text(content, encoding="utf-8")
        return True
        
    def list_learned_skills(self) -> List[str]:
        """Returns a list of all learned skill file names."""
        return [f.name for f in self.skills_dir.glob("*.md")]
        
    def get_skill_summary(self, skill_filename: str) -> Optional[SkillFrontmatter]:
        """Reads a skill file, parses the YAML frontmatter, and returns the structured summary."""
        skill_path = self.skills_dir / skill_filename
        if not skill_path.exists():
            return None
            
        try:
            content = skill_path.read_text(encoding="utf-8")
            parts = content.split("---")
            if len(parts) >= 3:
                fm_dict = yaml.safe_load(parts[1])
                if fm_dict:
                    return SkillFrontmatter.from_dict(fm_dict)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("skill_frontmatter_parse_failed [%s]: %s", skill_filename, exc)
        return None
        
    def delete_skill(self, skill_filename: str) -> bool:
        """Deletes a skill file. Returns True if successfully deleted."""
        skill_path = self.skills_dir / skill_filename
        if skill_path.exists():
            skill_path.unlink()
            return True
        return False
