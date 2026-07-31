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

    _ROUTE_CODES = {
        "0": "LOCAL",
        "1": "LARGE",
        "2": "HYBRID",
        "3": "REMOTE",
    }
    _DECISION_CODES = {
        "0": "ALLOW",
        "1": "REVIEW",
        "2": "STOP",
        "3": "STOP",
    }
    _PHASE_CODES = {
        "0": FlowState.INTAKE,
        "1": FlowState.PLAN,
        "2": FlowState.VERIFY,
        "3": FlowState.EXECUTE,
        "4": FlowState.CLOSE,
    }
    _CONFIDENCE_CODES = {"0": "HIGH", "1": "MEDIUM", "2": "LOW"}

    @classmethod
    def _decode_label(cls, value: str, mapping: dict[str, str], default: str) -> str:
        normalized = str(value or "").strip()
        return mapping.get(normalized, normalized.upper() or default)

    def process_model_output(self, raw_output: str) -> Tuple[str, str, FlowState, str]:
        """
        將模型輸出轉為 (Route, Decision, FlowState, Confidence)。
        如果模型吐出自然語言或格式錯誤，Rust 將回傳 None，這裡直接捕捉並 Escalation。
        """
        normalized = self.bridge.normalize_intent(raw_output)
        
        if normalized is None:
            # 觸發 Fail-Closed 安全網：模型格式錯誤，不允許推進
            return ("LARGE", "STOP", FlowState.ESCALATE, "LOW")
            
        route_raw, decision_raw, phase_raw, confidence_raw = normalized
        route_str = self._decode_label(route_raw, self._ROUTE_CODES, "LARGE")
        decision_str = self._decode_label(decision_raw, self._DECISION_CODES, "STOP")
        confidence_str = self._decode_label(confidence_raw, self._CONFIDENCE_CODES, "LOW")

        # 簡單映射回 Python 的 FlowState Enum
        try:
            phase_key = str(phase_raw).strip()
            phase = self._PHASE_CODES.get(phase_key)
            if phase is None:
                phase = FlowState(phase_key.upper())
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
