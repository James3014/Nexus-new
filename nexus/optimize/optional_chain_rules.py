from typing import List, Dict, Any

class OptionalChainRules:
    """
    📏 Task 4: OptionalChainRules
    職責: 規則化重型能力的啟用。
    """
    @staticmethod
    def evaluate_upgrades(context: Dict[str, Any]) -> List[str]:
        upgrades = []
        density = context.get("evidence_density", 1.0)
        risk = context.get("risk_flag", False)

        if density < 0.5:
            upgrades.append("codeintel")
        if risk:
            upgrades.append("mempalace_gate")
            
        return upgrades
