from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

@dataclass
class NexusEvent:
    """
    📢 Nexus Event Data Model
    職責: 標準化系統事件 (用於推送與紀錄)。
    """
    event_type: str        # improvement | rollback | convergence | error | stall | discovery
    task: str
    round_id: int
    score: float
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        return {
            "type": self.event_type,
            "task": self.task,
            "round": self.round_id,
            "score": self.score,
            "msg": self.message,
            "time": self.timestamp,
            "meta": self.metadata
        }

class BaseConnector(ABC):
    """
    🔌 Connector 抽象基底
    """
    @abstractmethod
    def send(self, event: NexusEvent) -> bool:
        """發送事件通知。"""
        pass
    
    @abstractmethod
    def poll_commands(self) -> List[str]:
        """(可選) 輪詢來自外部平台的指令。"""
        return []
