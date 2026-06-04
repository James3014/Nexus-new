from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass(frozen=True)
class MemoryHit:
    """
    🧠 Base Memory Hit Fact
    """
    id: str
    content: str
    relevance: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    state_version: int = 0  # 該記憶成立時的狀態版本

@dataclass(frozen=True)
class FailureSignatureHit(MemoryHit):
    """
    🚨 高因果權重命中：精確匹配故障簽名
    """
    root_cause: str = ""
    repro_command: str = ""
    resolution: str = ""
    causal_outcome: str = "SUCCESS"

@dataclass(frozen=True)
class MemoryContextPack:
    """
    📦 分層輸出上下文
    職責: 物理隔離不同權重的記憶，防止語義污染。
    """
    actionable_hits: List[FailureSignatureHit] = field(default_factory=list)
    family_context: List[MemoryHit] = field(default_factory=list)
    background_archive: List[MemoryHit] = field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        return len(self.actionable_hits) > 0
