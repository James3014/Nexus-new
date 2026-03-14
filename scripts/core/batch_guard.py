import os
import fcntl
from pathlib import Path
from core.state_contracts import NexusState

class BatchGuard:
    """
    🛡️ Nexus Batch Guard
    負責護欄機制：Token Budget 檢查與併發鎖 (StateIO Lock)。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.lock_file = self.project_root / ".musestate.lock"

    def acquire_lock(self):
        """獲取 StateIO 併發鎖，防止多 Worker 踩踏。"""
        self.fp = open(self.lock_file, 'w')
        try:
            fcntl.flock(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            print(f"🔒 [Guard] State lock acquired.")
            return True
        except IOError:
            print(f"⚠️ [Guard] State lock contention detected.")
            return False

    def release_lock(self):
        """釋放 StateIO 併發鎖。"""
        if hasattr(self, 'fp'):
            fcntl.flock(self.fp, fcntl.LOCK_UN)
            self.fp.close()
            print(f"🔓 [Guard] State lock released.")

    def check_budget(self, state: NexusState) -> bool:
        """檢查 Token 消耗是否超出工單預算。"""
        current_usage = state.metadata.get("token_usage", 0)
        budget = state.config.budget_token
        
        if current_usage >= budget:
            print(f"🚨 [AUTO-MELT] Token budget exceeded: {current_usage} >= {budget}")
            return False
        return True

    def update_heartbeat(self):
        """更新 .musestate 的心跳時間戳。"""
        state_file = self.project_root / ".musestate"
        if state_file.exists():
            state_file.touch()
            print(f"💓 [Guard] Heartbeat updated.")

    def check_stalled(self, timeout_mins: int = 10) -> bool:
        """偵測工單是否停滯 (超過 timeout 未更新狀態)。"""
        state_file = self.project_root / ".musestate"
        if not state_file.exists():
            return False
            
        import time
        mtime = os.path.getmtime(state_file)
        if (time.time() - mtime) > (timeout_mins * 60):
            print(f"🧊 [Guard] STALLED detected (>{timeout_mins}m). Triggering Melt.")
            return True
        return False
