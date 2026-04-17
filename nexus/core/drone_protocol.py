"""🛡️ Drone 介面契約 Protocol (v24.2 Governance Hardening)"""
from typing import Any, Dict, List, Protocol, runtime_checkable

@runtime_checkable
class DroneProtocol(Protocol):
    """TacticalDrone 的公開介面契約。
    所有呼叫方（如 CampaignGeneral）必須遵循此簽名。"""
    
    def sense_think_act(
        self,
        task_intent: str,
        tools: List[Any] | None = None,
    ) -> Dict[str, Any]:
        """執行 Sense-Think-Act 循環。
        
        Args:
            task_intent: 任務描述字串
            tools: 可選的工具列表（預設 None）
            
        Returns:
            dict with keys: drone_id, outcome, belief_final, traces
            outcome 必須是: SUCCESS | FAIL | TIMEOUT | REPAIR_NEEDED
        """
        ...
