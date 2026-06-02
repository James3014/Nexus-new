from typing import List, Dict, Any
from nexus.optimize.cost_policy import CostEvidencePolicy

class OptionalChainRules:
    """
    📏 Nexus Optional Chain Rules (v2.5)
    職責: 定義重型能力鏈的觸發規則。
    遵循「最小權限」與「按需啟動」原則。
    """
    
    @staticmethod
    def evaluate_upgrade(current_state: Dict[str, Any]) -> List[str]:
        """
        根據當前狀態（如證據密度、風險標籤）決定追加哪些能力。
        """
        upgrades = []
        evidence_density = current_state.get("evidence_density", 1.0)
        risk_flag = current_state.get("risk_flag", False)
        
        # 1. 證據不足規約：若目前證據無法支撐裁決，追加 CodeIntel
        if evidence_density < 0.5:
            upgrades.append("codeintel")
            
        # 2. 邊界風險規約：若偵測到潛在政策衝突，追加 MemPalace
        if risk_flag:
            upgrades.append("mempalace_gate")
            
        return upgrades
