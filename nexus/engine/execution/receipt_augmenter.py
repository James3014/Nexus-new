import json
from typing import Dict, Any, List
from nexus.engine.contracts.execution import ExecutionPhase, PhaseTiming

class ExecutionReceiptAugmenter:
    """
    🛡️ ExecutionReceiptAugmenter: 執行收據補強器
    將 PhaseTimer 與 Deferred Queue 狀態注入到 Receipt 中。
    """
    def augment(self, base_receipt: Dict[str, Any], timings: Dict[ExecutionPhase, PhaseTiming], deferred_checks: List[Any], health_class: str) -> Dict[str, Any]:
        augmented = base_receipt.copy()
        
        # 1. Phase Breakdown
        phase_durations = {k.value: v.wall_time_sec for k, v in timings.items()}
        augmented["execution_timings"] = phase_durations
        
        # 2. Timeout attribution (identify which phase was running if TIMEOUT or FAILED)
        timeout_phase = None
        for k, v in timings.items():
            if v.status in ["TIMEOUT", "FAILED", "RUNNING"]:
                timeout_phase = k.value
                break
        augmented["timeout_phase"] = timeout_phase
        
        # 3. Health & Deferred
        augmented["patch_health"] = health_class
        augmented["deferred_checks"] = [
            {"check_id": c.check_id, "type": c.verifier_type} for c in deferred_checks
        ]
        
        return augmented
