from typing import Dict, Any

class CostEvidencePolicy:
    """
    💰 Task 2: CostEvidencePolicy
    職責: 成本分類與路由解耦。將執行收據映射為純淨的成本語義標籤。
    """
    @staticmethod
    def classify_cost_evidence(receipt: Dict[str, Any]) -> str:
        model_calls = receipt.get("model_calls", 0)
        total_tokens = receipt.get("total_tokens", 0)
        cap_count = receipt.get("capability_count", 0)

        if model_calls == 0 and total_tokens == 0:
            return "rescue_only_no_model_call"
            
        if model_calls > 0 and cap_count >= 7:
            return "full_chain_delivery"
            
        return "lite_model_supervised"
