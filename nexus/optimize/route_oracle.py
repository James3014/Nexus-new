from enum import Enum
from typing import Dict, Any, List, Optional
from nexus.engine.capability_contracts import FlowState

class RouteOracle:
    """
    ⚖️ Nexus Route Oracle (v2.5)
    職責: 純粹的決策邏輯。依據風險與信心，判定推薦流程。
    不負責裝配能力鏈。
    """
    @staticmethod
    def recommend_flow(risk_score: int, bare_sufficiency: str, task_type: str) -> Dict[str, Any]:
        # 核心優化: Risk 30-60 的中風險任務不再直跳 Hypersprint
        if risk_score < 30:
            return {"flow": "baseline", "lite": True, "reason": "low_risk_auto_pass"}
        
        if 30 <= risk_score <= 60 and bare_sufficiency == "high":
            # [Optimization] 降級至 lite-supervised 而非 full hyper
            return {"flow": "lite_supervised", "lite": True, "reason": "bounded_medium_risk"}
            
        if risk_score > 60:
            return {"flow": "hyper_sprint", "lite": False, "reason": "high_risk_forced_hyper"}
            
        return {"flow": "baseline", "lite": False, "reason": "default_fallback"}

class CapabilityAssembler:
    """
    🛠️ Nexus Capability Assembler (v2.5)
    職責: 將推薦流程轉化為「Core + Optional」能力鏈。
    實現兩段式加載 (Lazy Activation)。
    """
    @staticmethod
    def assemble(flow: str, risk_score: int) -> Dict[str, List[str]]:
        core_chain = ["claim_gate", "delivery_gate"]
        optional_chain = []
        
        if flow in ["hyper_sprint", "lite_supervised"]:
            core_chain.append("harness_preflight_sensor")
            
            # [Optimization] 重能力鏈改為 Optional
            if risk_score > 70:
                optional_chain.extend(["codeintel", "mempalace_gate", "artifact_gate"])
            elif flow == "hyper_sprint":
                optional_chain.append("artifact_gate") # 僅保留最基本的 A-Gate

        return {
            "core": core_chain,
            "optional": optional_chain
        }
