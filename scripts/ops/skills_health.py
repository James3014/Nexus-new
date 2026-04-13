import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

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


def _read_json(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not path.exists():
        return default or {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default or {}


def build_skills_health(project_root: Path, workspace: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(project_root)
    workspace_path = Path(workspace) if workspace else None

    weights = _read_json(root / "scripts" / "core" / "autonomic_weights.json", {"skill_adjustments": {}})
    autotune = _read_json(root / ".nexus" / "metrics" / "skills_autotune_report.json", {})
    queue = _read_json(root / ".nexus" / "metrics" / "skills_optimization_queue.json", {"items": []})

    phase7_converged = False
    if workspace_path is not None:
        phase7 = _read_json(workspace_path / "phase7_prod_final_report_cn.json", {})
        phase7_converged = bool(phase7.get("converged", False))

    queue_items = queue.get("items", [])
    queue_count = len(queue_items) if isinstance(queue_items, list) else 0
    tuned_count = int(autotune.get("tuned_skill_count", 0) or 0)
    adjusted_count = len(weights.get("skill_adjustments", {}) or {})

    readiness = {
        "weights_loaded": adjusted_count > 0,
        "autotune_present": tuned_count > 0,
        "optimization_queue_empty": queue_count == 0,
        "phase7_loop_converged": phase7_converged if workspace_path else True,
    }
    ready_for_formal_use = all(readiness.values())

    return {
        "ready_for_formal_use": ready_for_formal_use,
        "readiness": readiness,
        "summary": {
            "adjusted_skill_count": adjusted_count,
            "tuned_skill_count": tuned_count,
            "queue_count": queue_count,
        },
    }
