from typing import Dict, List, Any
from nexus.optimize.optional_chain_rules import OptionalChainRules

class CapabilityAssembler:
    """
    🛠️ Nexus Capability Assembler (v2.5)
    職責: 將推薦流程轉化為「Core + Optional」能力鏈。
    """
    @staticmethod
    def assemble(flow: str, risk_score: int, current_context: Dict[str, Any] = None) -> Dict[str, List[str]]:
        core_chain = ["claim_gate", "delivery_gate"]
        optional_chain = []
        
        if flow in ["hyper_sprint", "lite_supervised"]:
            core_chain.append("harness_preflight_sensor")
            
            # [Optimization] 透過規則引擎決定追加能力，而非硬編碼
            if current_context:
                optional_chain.extend(OptionalChainRules.evaluate_upgrade(current_context))
            
            # 若無 context 但 Risk 極高，則作為預設追加
            elif risk_score > 70:
                optional_chain.extend(["codeintel", "mempalace_gate"])

        return {
            "core": core_chain,
            "optional": optional_chain
        }
