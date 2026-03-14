#!/usr/bin/env python3
"""
Nexus v7 Skills Router v0.1 - Decision Tree + Scorecard Prototype
🧬 Following Spec 14: Selection-Only Decision Logic.
"""

import json
import argparse
import sys
from pathlib import Path
from typing import List, Dict

def score_skill(skill_name: str, skill_info: Dict, phase: str, lang: str, task_scale: str, input_triggers: List[str]) -> Dict:
    """简单 scorecard：0-10 分 | Simplified Scorecard: 0-10 Points"""
    base_score = 0
    
    # 1. Phase match (Weight: 4)
    if "*" in skill_info["phases"] or phase in skill_info["phases"]:
        base_score += 4
    
    # 2. Language match (Weight: 2)
    if "*" in skill_info["langs"] or lang.lower() in [l.lower() for l in skill_info["langs"]]:
        base_score += 2
    
    # 3. Task scale (Weight: 2)
    inventory_triggers = skill_info.get("triggers", [])
    if task_scale == "large" and any("large_" in st for st in inventory_triggers):
        base_score += 2
    
    # 4. Trigger match (Max: 2)
    matched_triggers = [t for t in input_triggers if any(st in t for st in inventory_triggers)]
    base_score += min(len(matched_triggers), 2)
    
    return {
        "skill": skill_name,
        "score": base_score,
        "reasons": matched_triggers if matched_triggers else ["Default Lifecycle Match"],
        "threshold": 5 # Threshold from Spec 14
    }

def route_skills(inventory: Dict, phase: str, lang: str, task_scale: str, triggers: List[str]) -> List[Dict]:
    """主路由：選配符合門檻的技能 | Main Router: Select skills meeting threshold"""
    candidates = []
    for name, info in inventory["skills"].items():
        scored = score_skill(name, info, phase, lang, task_scale, triggers)
        if scored["score"] >= scored["threshold"]:
            candidates.append(scored)
    
    # 按分數排序 | Sort by score
    return sorted(candidates, key=lambda x: x["score"], reverse=True)

def main():
    parser = argparse.ArgumentParser(description="Nexus v7 Skills Router v0.1")
    parser.add_argument("--phase", required=True, choices=["P", "D", "R", "A", "C"], help="P-D-X-R-A-C Phase")
    parser.add_argument("--lang", default="python", help="Target Language")
    parser.add_argument("--task-scale", default="medium", choices=["small", "medium", "large"], help="Task Complexity Scale")
    parser.add_argument("--triggers", nargs="*", default=[], help="Input Trigger Keywords")
    
    args = parser.parse_args()
    
    # Load Skills Inventory
    inventory_path = Path(__file__).parent / "skills_inventory.json"
    if not inventory_path.exists():
        print(f"Error: {inventory_path} not found.")
        sys.exit(1)
        
    with open(inventory_path, "r") as f:
        inventory = json.load(f)
    
    selected = route_skills(inventory, args.phase, args.lang, args.task_scale, args.triggers)
    
    # Final Decision JSON Output
    decision = {
        "context": {
            "phase": args.phase,
            "lang": args.lang,
            "task_scale": args.task_scale,
            "input_triggers": args.triggers
        },
        "selected_skills": selected,
        "decision_engine": "Nexus-Router-v0.1",
        "timestamp": "2026-03-14T08:52:31Z" # Placeholder
    }
    
    print(json.dumps(decision, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
