from dataclasses import dataclass, field
from typing import List, Dict, Any
from nexus.governance.domain.blocker_taxonomy import BlockerCode

@dataclass(frozen=True)
class HeatmapCell:
    """[Domain] 熱圖單元格：時間窗內的 blocker 分布"""
    time_bucket: str
    blocker_code: BlockerCode
    occurrence_count: int

@dataclass(frozen=True)
class TrendPoint:
    """[Domain] 趨勢點：單一指標的時間序列值"""
    timestamp: str
    metric_name: str
    value: float

@dataclass(frozen=True)
class ObservabilityBundle:
    """[Domain] 觀測全集：聚合熱圖與趨勢"""
    heatmap: List[HeatmapCell]
    trends: List[TrendPoint]
    summary_verdict: str = "HEALTHY"
