import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class DomainFirewall:
    """🛡️ Nexus v25.5 Domain-based Tool Firewall with BaseSkill mitigation."""
    def __init__(self, tactical_map_path: str = str(__import__("pathlib").Path(__file__).resolve().parents[2] / "nexus/config/tactical_map.json")):
        try:
            with open(tactical_map_path, 'r') as f:
                self.map = json.load(f)
            self.base_skills = self.map.get("base_skills", [])
            logger.info(f"✅ [Firewall] Loaded {self.map['total_skills']} skills / {len(self.base_skills)} BaseSkills.")
        except Exception as e:
            logger.error(f"❌ [Firewall] Failed to load map: {e}")
            self.map = {"quadrants": {}}
            self.base_skills = []

    def authorize(self, skill_id: str, current_domain: str) -> bool:
        """斷言技能是否屬於當前戰術領地或屬於全域 BaseSkill。"""
        # Rule 1: Always allow BaseSkills
        if skill_id in self.base_skills:
            return True
            
        # Rule 2: Check current quadrant
        quadrant = self.map["quadrants"].get(current_domain, {})
        if skill_id in quadrant.get("skills", []):
            return True
            
        return False

    def validate_v23_reasoning(self, domain: str, mode: str):
        policy = self.map.get("reasoning_policy", {}).get(domain, "INTUITIVE")
        return mode == policy
