from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import difflib

@dataclass(frozen=True)
class DriftDiff:
    """[NEXUS v27] 政策漂移差異報表"""
    task_id: str
    field_name: str
    old_value: Any
    new_value: Any
    lane_impact: str

class PolicyDriftReporter:
    """
    🔍 Task: Policy Drift Diff Report
    職責: 識別規格變更細節，並產出機器可讀的差異報告。
    """
    @staticmethod
    def compare_specs(old_specs: List[Any], new_specs: List[Any]) -> List[DriftDiff]:
        diffs = []
        old_map = {s.task_id: s for s in old_specs}
        new_map = {s.task_id: s for s in new_specs}
        
        all_ids = set(old_map.keys()).union(new_map.keys())
        
        for tid in all_ids:
            if tid not in old_map:
                diffs.append(DriftDiff(tid, "task_id", None, tid, "NEW_ENTRY"))
                continue
            if tid not in new_map:
                diffs.append(DriftDiff(tid, "task_id", tid, None, "DELETED_ENTRY"))
                continue
                
            old_s = old_map[tid]
            new_s = new_map[tid]
            
            # 檢查關鍵治理欄位
            for field in ["domain_id", "lane", "promotion_policy"]:
                ov = getattr(old_s, field)
                nv = getattr(new_s, field)
                if ov != nv:
                    diffs.append(DriftDiff(tid, field, ov, nv, new_s.lane))
                    
        return diffs
