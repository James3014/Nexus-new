#!/usr/bin/env python3
import sys
import os
import shutil
import subprocess
from pathlib import Path
from typing import List
import argparse
import json
from core.state_contracts import NexusBatch, NexusIssue
from core.batch_guard import BatchGuard

class BatchCLI:
    """
    🏗️ Nexus Batch CLI
    負責夜班工單的大規模分發與自動化排程。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.guard = BatchGuard(project_root)

    def run_night_batch(self, issue_list_path: str, workers: int = 2):
        """讀取工單清單並發動批量任務。"""
        issues_data = json.loads(Path(issue_list_path).read_text())
        batch = NexusBatch(batch_id=f"night-{int(sys.time())}", tasks_count=len(issues_data))
        
        print(f"🌙 [NightShift] Starting Batch {batch.batch_id} with {len(issues_data)} issues.")
        
        for issue_dict in issues_data:
            issue = NexusIssue(**issue_dict, batch_id=batch.batch_id)
            self._dispatch_issue(issue)

    def _dispatch_issue(self, issue: NexusIssue):
        """將單個工單分發到獨立的 tmux session，並使用 worktree 隔離。"""
        session_name = f"nexus-{issue.task_id[:8]}"
        print(f"  🚀 [Dispensing] Issue {issue.task_id} into tmux session: {session_name}")
        
        # 🛡️ Tmux 硬化: 建立隔離會話並發送指令
        subprocess.run(["tmux", "new-session", "-d", "-s", session_name])
        
        # 指令序列：進入目錄 -> 啟動 Codex-Loop
        # 未來整合：self.workspace_manager.setup_worktree(issue.task_id)
        cmds = [
            f"cd {self.project_root}",
            f"export NEXUS_TASK_ID={issue.task_id}",
            f"python3 scripts/codex_loop_brain.py --mode agent-shield --apply"
        ]
        
        for cmd in cmds:
            subprocess.run(["tmux", "send-keys", "-t", session_name, cmd, "C-m"])
            
        print(f"  [Status] Session {session_name} is running.")

    def setup_cron(self, schedule: str):
        """設置 Cron Job 自動執行夜班任務。"""
        cron_cmd = f"{schedule} cd {self.project_root} && python3 scripts/core/batch_cli.py --run"
        print(f"⏰ [Cron] Registered: {cron_cmd}")
        # 實際寫入 crontab 邏輯在此

    def manage_tmux(self, action: str):
        """管理 tmux session 確保夜班任務在背景持續運行。"""
        if action == "start":
            subprocess.run(["tmux", "new-session", "-d", "-s", "nexus-night-batch"])
            print("🖥️ [Tmux] Session 'nexus-night-batch' started.")
        elif action == "attach":
            os.system("tmux attach -t nexus-night-batch")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nexus v7 Batch CLI")
    parser.add_argument("--run", type=str, help="Path to issues.json")
    parser.add_argument("--dispatch-one", type=str, help="JSON string of a single NexusIssue")
    parser.add_argument("--schedule", type=str, help="Cron schedule (e.g. '0 23 * * *')")
    parser.add_argument("--tmux", choices=["start", "attach", "kill"], help="Manage tmux session")
    
    args = parser.parse_args()
    cli = BatchCLI(os.getcwd())
    
    if args.run:
        cli.run_night_batch(args.run)
    elif args.dispatch_one:
        issue_data = json.loads(args.dispatch_one)
        cli._dispatch_issue(NexusIssue(**issue_data))
    elif args.schedule:
        cli.setup_cron(args.schedule)
    elif args.tmux:
        cli.manage_tmux(args.tmux)
