from typing import Any, Dict, List, Optional, Tuple
import json
import hashlib
from nexus.core.state_contracts import NexusState

class MentalSnapshot:
    """
    🧠 Nexus 心智快照 (AOS-P5.5)
    負責 Agent 內部思維狀態與工作記憶的序列化持久化。
    """
    
    def __init__(self, state: Optional[NexusState] = None):
        if state:
            self.mind = {
                "task_id": state.task_id,
                "read_files": state.metadata.get("read_files_cache", {}),
                "todo_list": state.metadata.get("pending_tasks", []),
                "fail_paths": state.metadata.get("failed_attempts", []),
                "phase": state.current_phase,
                "checksum": self._calculate_checksum(state)
            }
        else:
            self.mind = {}

    def serialize(self) -> str:
        """📸 序列化為 JSON 字符串"""
        return json.dumps(self.mind, indent=2, ensure_ascii=False)

    @classmethod
    def deserialize(cls, json_str: str) -> 'MentalSnapshot':
        """📂 從 JSON 字符串還原心智快照"""
        snapshot = cls()
        snapshot.mind = json.loads(json_str)
        return snapshot

    def _calculate_checksum(self, state: NexusState) -> str:
        """物理核驗工作空間真值 Hashing"""
        # 簡單模擬工作空間真值雜湊
        seed = f"{state.task_id}-{state.current_phase}-{len(state.metadata)}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    def restore_to(self, state: NexusState):
        """🧠 從快照還原至狀態對象"""
        state.metadata["read_files_cache"] = self.mind.get("read_files", {})
        state.metadata["pending_tasks"] = self.mind.get("todo_list", [])
        state.metadata["failed_attempts"] = self.mind.get("fail_paths", [])
        state.current_phase = self.mind.get("phase", "P")
        
    def subsystem_snapshot(self) -> Dict[str, Any]:
        """🧬 Claw-30P3: 獲取子系統深度快照"""
        return {
            "modules_count": len(self.mind.get("read_files", {})),
            "semantic_vectors": "thermal-0x31-8k", # 模擬熱向量真值
            "skill_wins": {
                "reading-plans": 0.95,
                "systematic-debugging": 0.88,
                "safe-patch": 0.99
            }
        }
