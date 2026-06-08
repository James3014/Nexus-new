from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import time

@dataclass
class CausalEvent:
    event_id: str
    action: str
    target: str
    outcome: str
    parent_event_id: Optional[str] = None
    reasoning_trace: str = ""
    timestamp: float = 0.0
    
class MemoryGraph:
    """
    🛡️ MemoryGraph: 因果記憶圖
    取代扁平的日誌，支援「失敗追溯 (Traceback)」以擷取有用的約束。
    """
    def __init__(self):
        self.nodes: Dict[str, CausalEvent] = {}

    def record_event(self, action: str, target: str, outcome: str, parent_id: Optional[str] = None, reason: str = "") -> str:
        evt_id = f"evt_{int(time.time()*1000)}_{len(self.nodes)}"
        evt = CausalEvent(
            event_id=evt_id,
            action=action,
            target=target,
            outcome=outcome,
            parent_event_id=parent_id,
            reasoning_trace=reason,
            timestamp=time.time()
        )
        self.nodes[evt_id] = evt
        return evt_id

    def trace_back(self, event_id: str) -> List[CausalEvent]:
        """從給定事件回溯其因果鏈。"""
        trace = []
        curr = self.nodes.get(event_id)
        while curr:
            trace.append(curr)
            curr = self.nodes.get(curr.parent_event_id) if curr.parent_event_id else None
        return trace[::-1] # 回傳依時間順序的因果鏈
