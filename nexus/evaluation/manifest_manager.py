from typing import List, Dict, Any, Literal
from dataclasses import dataclass
from nexus.services.local_heal.task_manifest import local_heal_113_task_manifest

@dataclass(frozen=True)
class TaskLaneAssignment:
    """[T1] 任務車道分配數據結構"""
    task_id: str
    lane: Literal["baseline", "challenge"]
    failure_family: str
    receipt_id: Optional[str] = None

class ManifestManager:
    """
    🗺️ Task T1: 113 題總表管理員
    職責: 實施「100 守成 + 13 攻堅」的分層治理政策。
    """
    @staticmethod
    def get_full_inventory() -> List[TaskLaneAssignment]:
        specs = local_heal_113_task_manifest()
        inventory = []
        
        for spec in specs:
            idx = spec.swe_index if spec.swe_index is not None else 0
            # 治理政策：前 100 題 (0-99) 為 Baseline，其餘為 Challenge
            lane = "baseline" if idx < 100 else "challenge"
            
            # 初始失敗歸因 (預設為 SUCCESS，待執行後動態更新)
            inventory.append(TaskLaneAssignment(
                task_id=spec.task_id,
                lane=lane,
                failure_family="SOLVED" if lane == "baseline" else "PENDING_RECOVERY"
            ))
            
        return inventory

    @staticmethod
    def get_challenge_set() -> List[TaskLaneAssignment]:
        return [item for item in ManifestManager.get_full_inventory() if item.lane == "challenge"]
