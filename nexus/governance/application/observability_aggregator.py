from typing import List, Dict, Any
import hashlib
from nexus.governance.domain.blocker_taxonomy import BlockerCode
from nexus.governance.domain.observability_models import HeatmapCell, TrendPoint, ObservabilityBundle

class ADRDiffGate:
    """
    🛡️ Task: ADR Specification Freeze (Infrastructure)
    職責: 確保規格變更必須經過顯式授權。
    """
    @staticmethod
    def verify_no_unauthorized_changes(current_schema_hash: str, 
                                       approved_adr_hash: str) -> bool:
        if current_schema_hash != approved_adr_hash:
            print("❌ GOVERNANCE ERROR: Unauthorized schema change detected. Must update ADR first.")
            return False
        return True

class ObservabilityAggregator:
    """
    📈 Task: Observability Expansion (Application)
    職責: 將收據與指標轉化為熱圖與趨勢數據。
    """
    @staticmethod
    def generate_heatmap(raw_blockers: List[BlockerCode]) -> List[HeatmapCell]:
        # 模擬聚合邏輯
        counts = {}
        for b in raw_blockers:
            counts[b] = counts.get(b, 0) + 1
            
        return [HeatmapCell(time_bucket="2026-06-03H00", blocker_code=b, occurrence_count=c) 
                for b, c in counts.items()]

    @staticmethod
    def aggregate_trends(history_metrics: List[Dict[str, Any]]) -> List[TrendPoint]:
        return [TrendPoint(timestamp=m["t"], metric_name="pass_rate", value=m["v"]) 
                for m in history_metrics]
