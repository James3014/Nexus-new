from typing import List, Dict

from nexus.optimize.contracts import ChainAssembly

class CapabilityAssembler:
    """
    🛠️ Nexus Capability Assembler (v2.5)
    """
    @staticmethod
    def assemble_chains(flow: str) -> ChainAssembly:
        core = ["claim_gate", "delivery_gate"]
        optional = []

        if flow in ["hyper_sprint", "lite_supervised"]:
            core.append("harness_preflight_sensor")
            optional.extend(["codeintel", "mempalace_gate"])
            
        return ChainAssembly(core=core, optional=optional)
