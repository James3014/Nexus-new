from dataclasses import dataclass
from typing import Any, Mapping, Dict, Optional

@dataclass(frozen=True)
class TaskState:
    """
    💎 Task State Model
    職責: 代表特定版本的問題治理狀態。
    """
    task_id: str
    version: int
    payload: Mapping[str, Any]
    parent_version: Optional[int] = None
    checkpoint_label: Optional[str] = None

class TaskStateStore:
    """
    🏛️ Task M1: Task State Store (State Layer)
    職責: 唯一真實狀態來源 (SSoT)，防止長流程中的 State Drift。
    """
    def __init__(self):
        self._states: Dict[str, Dict[int, TaskState]] = {}

    def get_latest(self, task_id: str) -> Optional[TaskState]:
        if task_id not in self._states:
            return None
        latest_ver = max(self._states[task_id].keys())
        return self._states[task_id][latest_ver]

    def commit(self, task_id: str, payload: Mapping[str, Any]) -> TaskState:
        if task_id not in self._states:
            self._states[task_id] = {}
            version = 1
            parent = None
        else:
            latest = self.get_latest(task_id)
            version = latest.version + 1
            parent = latest.version
            
        new_state = TaskState(
            task_id=task_id,
            version=version,
            payload=payload,
            parent_version=parent
        )
        self._states[task_id][version] = new_state
        return new_state

    def checkpoint(self, task_id: str, label: str) -> TaskState:
        latest = self.get_latest(task_id)
        if not latest:
            raise ValueError(f"Cannot checkpoint empty task: {task_id}")
            
        checkpoint_state = TaskState(
            task_id=latest.task_id,
            version=latest.version,
            payload=latest.payload,
            parent_version=latest.parent_version,
            checkpoint_label=label
        )
        # Checkpoint 通常不增加版本，而是標記當前版本
        self._states[task_id][latest.version] = checkpoint_state
        return checkpoint_state

    def rollback(self, task_id: str, to_version: int) -> TaskState:
        if task_id not in self._states or to_version not in self._states[task_id]:
            raise ValueError(f"Invalid rollback target: {task_id} v{to_version}")
            
        target = self._states[task_id][to_version]
        # Rollback 動作產生一個新版本，但 payload 回復到目標
        return self.commit(task_id, target.payload)

    def reject_if_stale(self, task_id: str, base_version: int) -> None:
        latest = self.get_latest(task_id)
        if latest and latest.version > base_version:
            raise RuntimeError(f"Stale state detected: Current v{latest.version} > Base v{base_version}")
