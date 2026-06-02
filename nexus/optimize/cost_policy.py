from typing import Dict, Any

from nexus.optimize.contracts import CostClassification

class CostEvidencePolicy:
    """
    💰 Nexus Cost Evidence Policy (v2.5)
    """
    @staticmethod
    def classify_cost_evidence(receipt: Dict[str, Any]) -> CostClassification:
        model_calls = receipt.get("model_calls", 0)
        total_tokens = receipt.get("total_tokens", 0)
        cap_count = receipt.get("capability_count", 0)

        if model_calls == 0 and total_tokens == 0:
            return CostClassification(profile="rescue_only_no_model_call", clean_evidence=True)
            
        if model_calls > 0 and cap_count >= 7:
            return CostClassification(profile="full_chain_delivery", clean_evidence=False)
            
        return CostClassification(profile="lite_model_supervised", clean_evidence=True)
