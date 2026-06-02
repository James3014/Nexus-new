from typing import Dict, List

class CapabilityAssembler:
    """
    🛠️ Nexus Capability Assembler (v2.5)
    職責: 將推薦流程轉化為「Core + Optional」能力鏈。
    實現兩段式加載 (Lazy Activation)。
    """
    @staticmethod
    def assemble_chain(flow: str) -> Dict[str, List[str]]:
        core = ["claim_gate", "delivery_gate"]
        optional = []
        
        if flow == "hyper_sprint":
            core.append("artifact_gate")
            # 預設將重型工具放入可選鏈，不進入核心路徑
            optional.extend(["codeintel", "mempalace_gate"])
            
        return {"core": core, "optional": optional}
