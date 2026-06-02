from typing import Optional, Tuple
from nexus.engine.governance_bridge import GovernanceBridge
from nexus.engine.capability_contracts import FlowState

class SemanticAdapter:
    """
    [NEXUS v26] Semantic Adapter (Hybrid Governance 2.0)
    負責接收模型的字串輸出，呼叫 Rust Normalizer，若不合規一律回退至 ESCALATE。
    """
    def __init__(self):
        self.bridge = GovernanceBridge()

    def process_model_output(self, raw_output: str) -> Tuple[str, str, FlowState, str]:
        """
        將模型輸出轉為 (Route, Decision, FlowState, Confidence)。
        如果模型吐出自然語言或格式錯誤，Rust 將回傳 None，這裡直接捕捉並 Escalation。
        """
        normalized = self.bridge.normalize_intent(raw_output)
        
        if normalized is None:
            # 觸發 Fail-Closed 安全網：模型格式錯誤，不允許推進
            return ("LARGE", "STOP", FlowState.ESCALATE, "LOW")
            
        route_str, decision_str, phase_str, confidence_str = normalized
        
        # 簡單映射回 Python 的 FlowState Enum
        try:
            phase = FlowState(phase_str)
        except ValueError:
            phase = FlowState.UNKNOWN

        # 🛡️ [NEXUS v2.4] EscalationPolicy
        # 若狀態為 UNKNOWN 或決策為 STOP/REJECT，一律強制降級為 ESCALATE
        if phase == FlowState.UNKNOWN or decision_str in ["STOP", "REJECT"]:
            return ("LARGE", "STOP", FlowState.ESCALATE, "LOW")

        return (route_str, decision_str, phase, confidence_str)

if __name__ == "__main__":
    adapter = SemanticAdapter()
    
    # 測試合法輸入
    print("Valid:", adapter.process_model_output("r:0,d:0,p:1,c:0"))
    
    # 測試非法輸入 (回聲效應/自然語言)
    print("Invalid:", adapter.process_model_output("I think we should proceed to Phase R"))
