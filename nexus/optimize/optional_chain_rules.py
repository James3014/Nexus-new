from typing import List, Dict, Any

class OptionalChainRules:
    """
    📏 Nexus Optional Chain Rules (v2.5)
    職責: 定義重型能力鏈的觸發規則。
    """
    @staticmethod
    def evaluate_upgrades(context: Dict[str, Any]) -> List[str]:
        upgrades = []
        evidence_density = context.get("evidence_density", 1.0)
        risk_flag = context.get("risk_flag", False)
        
        # 1. 證據密度規則: 密度不足 (< 0.5) 則啟動 codeintel
        if evidence_density < 0.5:
            upgrades.append("codeintel")
            
        # 2. 邊界風險規則: 有風險標記則啟動 mempalace
        if risk_flag:
            upgrades.append("mempalace_gate")
            
        return upgrades
