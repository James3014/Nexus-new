class CostEvidencePolicy:
    """
    💰 Nexus Cost Evidence Policy (v2.5)
    職責: 分類成本證據並回饋路由策略。
    """
    @staticmethod
    def classify_cost_evidence(model_calls: int, total_tokens: int, cap_count: int) -> str:
        # 1. 確定性救援模式 (0 Model Call)
        if model_calls == 0 and total_tokens == 0:
            return "rescue_only_no_model_call"
            
        # 2. 全鏈路交付模式
        if model_calls > 0 and cap_count >= 7:
            return "full_chain_delivery"
            
        return "lite_model_supervised"
