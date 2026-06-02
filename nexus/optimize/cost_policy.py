from typing import Dict, Any

class CostEvidencePolicy:
    """
    💰 Nexus Cost Evidence Policy (v2.5)
    職責: 將真實執行軌跡分類為精確的成本等級。
    目標: 確保成本報表語義純淨，不將「Rescue」與「Model Call」混為一談。
    """
    @staticmethod
    def classify_evidence(model_calls: int, total_tokens: int, capability_count: int) -> str:
        if model_calls == 0 and total_tokens == 0:
            if capability_count <= 4:
                return "rescue_only_no_model_call"
            return "deterministic_local_rescue"
            
        if model_calls > 0:
            if capability_count >= 7:
                return "full_chain_delivery"
            return "lite_model_supervised"
            
        return "unknown_cost_profile"

    @staticmethod
    def should_upgrade_to_optional(current_evidence_density: float, risk_flag: bool) -> bool:
        """
        [Lazy Activation] 決定是否需要啟動 Optional Chain (如 codeintel)。
        """
        # 如果證據密度不足，或偵測到隱性風險，則建議升級。
        return current_evidence_density < 0.5 or risk_flag
