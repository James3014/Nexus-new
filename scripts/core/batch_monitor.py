import os
import time
import json
import subprocess
from pathlib import Path

class WarRoomMonitor:
    """
    👁️ Nexus WarRoom Monitor
    即時監控夜班工廠的健康度。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)

    def watch(self, interval: int = 5):
        """實時監控循環。"""
        print("🕯️ [WarRoom] Monitoring Factory status... (Press Ctrl+C to stop)")
        try:
            while True:
                os.system('clear')
                print(f"🏰 Nexus Night Factory WarRoom | {time.ctime()}")
                print("-" * 60)
                self._show_sessions()
                print("-" * 60)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 WarRoom monitoring ended.")

    def _show_sessions(self):
        try:
            res = subprocess.run(["tmux", "list-sessions", "-F", "#S"], capture_output=True, text=True)
            sessions = [s for s in res.stdout.strip().split("\n") if s.startswith("nexus-")]
            
            if not sessions:
                print("📭 No active tasks running.")
                return

            print(f"{'Session':<20} | {'Status':<10} | {'Tokens':<8} | {'Strikes':<4}")
            print("-" * 50)
            for s in sessions:
                # 模擬從 .musestate 讀取數據 (實際需對應 Session ID 建立 Worktree 目錄)
                print(f"{s:<20} | {'RUNNING':<10} | {'4,250':<8} | {'1':<4}")
        except:
            print("❌ Failed to list tmux sessions.")

if __name__ == "__main__":
    monitor = WarRoomMonitor(".")
    # 若在 CLI 執行，可呼叫 monitor.watch()
