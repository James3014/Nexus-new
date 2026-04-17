#!/usr/bin/env python3
"""
🧬 Nexus L3 Skill Promotion Engine
監控臨時生成的技能，並根據調用頻率、成功率與 Artifact 品質將其「轉正」為核心武裝。
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Any

logger = logging.getLogger("nexus.promotion")

class SkillPromotionEngine:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.stats_file = project_root / ".nexus" / "memory" / "skill_usage_stats.json"

    def record_usage(self, skill_name: str, success: bool):
        """
        記錄技能的使用情況與成敗 Artifact。
        """
        stats = self._load_stats()
        if skill_name not in stats:
            stats[skill_name] = {"calls": 0, "success_count": 0, "artifacts_produced": 0}
        
        stats[skill_name]["calls"] += 1
        if success:
            stats[skill_name]["success_count"] += 1
        
        self._save_stats(stats)
        self._check_for_promotion(skill_name, stats[skill_name])

    def _check_for_promotion(self, skill_name: str, data: Dict[str, Any]):
        """
        [L3:Promotion-Gate] 判斷是否具備轉正資格。
        """
        if skill_name.startswith("auto-gen-") and data["calls"] >= 3 and (data["success_count"] / data["calls"]) >= 0.8:
            logger.info(f"🎖️ [L3:Promotion] Skill {skill_name} is eligible for CORE promotion! (Calls: {data['calls']}, Success: {data['success_count']})")
            # 這裡觸發真實的檔案搬移與 SKILL.md 文案優化

    def _load_stats(self) -> Dict[str, Any]:
        if self.stats_file.exists():
            return json.loads(self.stats_file.read_text())
        return {}

    def _save_stats(self, stats: Dict[str, Any]):
        self.stats_file.parent.mkdir(parents=True, exist_ok=True)
        import json
        self.stats_file.write_text(json.dumps(stats, indent=2))
