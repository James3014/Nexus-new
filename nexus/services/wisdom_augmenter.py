import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class WisdomAugmenter:
    """
    🧠 Nexus Wisdom Augmenter (v25.5)
    職責：模擬 LanceDB 向量化檢索，從歷史成功案例中自動「增強」當前的實作包。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.templates_dir = project_root / ".nexus" / "knowledge" / "templates"

    def augment_implementation_pack(self, current_pack: Dict[str, Any]) -> Dict[str, Any]:
        """
        核心有用處：自動將歷史成功的 Edge Cases 與 Formulas 注入當前 pack。
        """
        goal = current_pack.get("goal", "").lower()
        logger.info(f"🔍 [Wisdom:Augment] Analyzing goal for pattern match: {goal}")

        # 1. 模擬向量聚類 (在沒有實體模型時，透過關鍵字叢集模擬向量命中)
        hit_template = None
        for template_file in self.templates_dir.glob("*.json"):
            with open(template_file, "r") as f:
                tpl = json.load(f)
                # 模擬向量距離計算：如果關鍵字命中率高，則視為向量接近
                matches = [kw for kw in tpl.get("matched_keywords", []) if kw.lower() in goal]
                if len(matches) >= 1:
                    hit_template = tpl
                    logger.info(f"🎯 [Wisdom:Hit] High similarity match found via historical pattern: {template_file.name}")
                    break
        
        if not hit_template:
            logger.info("ℹ️ [Wisdom:Augment] No high-confidence historical pattern found.")
            return current_pack

        # 2. 實施『有用處』的增強 (Augmentation)
        original_edge_count = len(current_pack.get("edge_cases", []))
        
        # 注入 Edge Cases
        historical_edges = hit_template.get("best_practice_edge_cases", [])
        current_edges = set(current_pack.get("edge_cases", []))
        for edge in historical_edges:
            if edge not in current_edges:
                current_pack.setdefault("edge_cases", []).append(edge)
        
        # 注入必勝公式 (Winning Formulas)
        historical_formulas = hit_template.get("winning_formulas", [])
        current_targets = set(current_pack.get("acceptance_targets", []))
        for formula in historical_formulas:
            if formula not in current_targets:
                current_pack.setdefault("acceptance_targets", []).append(formula)

        added_edges = len(current_pack.get("edge_cases", [])) - original_edge_count
        logger.info(f"🧬 [Wisdom:Inject] Successfully augmented {added_edges} historical Edge Cases.")
        
        current_pack["wisdom_boosted"] = True
        current_pack["source_wisdom"] = hit_template.get("task_type", "unknown")
        return current_pack
