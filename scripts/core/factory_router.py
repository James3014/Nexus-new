import json
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any
from core.state_contracts import NexusIssue, TaskConfig
from core.queue_manager import QueueManager

class FactoryRouter:
    """
    🏎️ Nexus Factory Router
    夜班工廠的智慧調度中心。負責管理併發任務、優先級隊列與模型負載均衡。
    """
    def __init__(self, project_root: str, max_workers: int = 5):
        self.project_root = Path(project_root)
        self.max_workers = max_workers
        self.queue_mgr = QueueManager()
        
        # 🎡 QPS/Token 限制規格 (Lvl 19)
        self.quotas = {
            "claude-3.5-sonnet": {"rpm": 10, "last_call": 0},
            "gemini-1.5-pro": {"rpm": 20, "last_call": 0}
        }

    def add_to_queue(self, issue: NexusIssue):
        """將新工單加入 SQLite 隊列。"""
        self.queue_mgr.enqueue(issue)
        print(f"📥 [Router] Task {issue.task_id} enqueued (Priority: {issue.priority}).")

    def run_loop(self):
        """核心調度迴圈：持續監控並分發任務。"""
        print("⚙️ [Router] Factory loop started.")
        while True:
            self.dispatch_next()
            time.sleep(10)  # 每 10 秒掃描一次

    def dispatch_next(self):
        """智慧分發邏輯。"""
        running_sessions = self._get_running_sessions()
        if len(running_sessions) >= self.max_workers:
            return

        # 這裡未來會從隊列中挑選符合 QPS 限制的任務
        task = self.queue_mgr.pop_next()
        if task:
            self._execute_task(task)

    def _get_running_sessions(self) -> List[str]:
        try:
            res = subprocess.run(["tmux", "list-sessions", "-F", "#S"], capture_output=True, text=True)
            return [s for s in res.stdout.strip().split("\n") if s.startswith("nexus-")]
        except:
            return []

    def _execute_task(self, issue: NexusIssue):
        """調用 batch_cli 啟動 Tmux 分身。"""
        print(f"🚀 [Router] Dispatching {issue.task_id}: {issue.goal}")
        subprocess.run([
            "python3", "scripts/core/batch_cli.py", 
            "--dispatch-one", issue.model_dump_json()
        ], check=False)

if __name__ == "__main__":
    router = FactoryRouter(".")
    # 測試：模擬加入一個 Hotfix
    hotfix = NexusIssue(task_id="hotfix-urgent", goal="Fix production login crash", priority=0)
    router.add_to_queue(hotfix)
    router.dispatch_next()
