import os
from pathlib import Path
from typing import List, Optional
import yaml
from nexus.learning.skill_schema import SkillFrontmatter

class SkillStore:
    def __init__(self, workspace_root: Path):
        self.skills_dir = workspace_root / "skills" / "learned"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        
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
        except Exception:
            pass
        return None
        
    def delete_skill(self, skill_filename: str) -> bool:
        """Deletes a skill file. Returns True if successfully deleted."""
        skill_path = self.skills_dir / skill_filename
        if skill_path.exists():
            skill_path.unlink()
            return True
        return False
