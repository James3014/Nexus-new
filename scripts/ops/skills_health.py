import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SkillsHealthScanner:
    """🧬 [Wave 2] Skills-Health: Workspace Purity Audit"""
    
    def __init__(self, skill_root: Path):
        self.skill_root = Path(os.path.expanduser(skill_root))

    def scan_purity(self) -> dict:
        """掃描工作區技能純度內容內容內容及性能內容內容"""
        logger.info(f"🧬 [Skills-Health] Scanning {self.skill_root}...")
        
        all_skills = list(self.skill_root.glob("**/*.md"))
        purity_score = 100.0
        phantom_risks = 0
        
        for skill in all_skills:
            # 🚀 行動 15: 檢測幻覺模式
            with open(skill, "r") as f:
                content = f.read()
                if "PHANTOM" in content or "TODO" in content:
                    phantom_risks += 1
        
        if len(all_skills) > 0:
            purity_score = max(0, 100 - (phantom_risks / len(all_skills) * 100))
            
        logger.info(f"🧬 [Skills-Health] Purity: {purity_score:.1f}% (Risks: {phantom_risks})")
        return {
            "purity": purity_score,
            "risk_count": phantom_risks,
            "skill_count": len(all_skills),
            "status": "HEALTHY" if purity_score > 90 else "INFECTED"
        }

if __name__ == "__main__":
    scanner = SkillsHealthScanner("~/.agents/skills")
    print(scanner.scan_purity())
