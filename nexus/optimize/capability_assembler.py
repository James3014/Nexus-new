from typing import List, Dict

class CapabilityAssembler:
    """
    🛠️ Task 3: CapabilityAssembler
    職責: 將 Flow 轉化為「Core + Optional」兩段式鏈結。
    """
    @staticmethod
    def assemble_chains(flow: str) -> Dict[str, List[str]]:
        core = ["claim_gate", "delivery_gate"]
        optional = []

        if flow in ["hyper_sprint", "lite_supervised"]:
            core.append("harness_preflight_sensor")
            # 預設將重型工具移至可選鏈
            optional.extend(["codeintel", "mempalace_gate"])
            
        return {"core": core, "optional": optional}
