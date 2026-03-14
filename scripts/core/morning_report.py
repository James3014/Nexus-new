import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
from core.state_contracts import NexusBatch, NexusState
from core.state_io import StateIO
import subprocess

class MorningReporter:
    """
    ☀️ Nexus Morning Reporter
    負責結算夜班戰果，產出工廠產能報表。
    """
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.state_io = StateIO(project_root)

    def generate_report(self, batch_id: str) -> str:
        """根據 batch_id 彙整所有工單狀態並產出報告。"""
        # 這裡未來會從 .tracelog.jsonl 或資料庫讀取 batch data
        # 目前先從全域狀態模擬結算
        state = self.state_io.load_global_state()
        
        report = [
            f"# 🌙 Night Batch Report: {batch_id}",
            f"**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 📊 Factory Summary",
            f"- **Success Rate**: 80% (Simulated)",
            f"- **Token Usage**: {state.metadata.get('total_tokens', 0):,} / Budget 50,000",
            f"- **Average Strikes**: 1.2",
            "",
            "## 🛠️ Work Orders (PR Stats)",
            "| Task ID | Domain | Status | Risk | Action |",
            "|---------|--------|--------|------|--------|",
        ]
        
        # 模擬一些工單數據與 Hot Spot
        report.append(f"| {state.task_id[:8]} | Python | ✅ PR Ready | Low | `gh pr create --draft` |")
        report.append(f"| issue-mock-2 | React | ⚠️ Human Review | Mid | Check Render Loop |")
        
        report.extend([
            "",
            "## 🔥 Hot Spots (Repeat Failures)",
            "- `scripts/core/state_contracts.py`: Failed 2x during P-stage validation. (Signature: `NameError: TaskConfig`)",
            "- `frontend/Dashboard.tsx`: High strike count (4) during R-stage. Suggest structure decoupling.",
            "",
            "## 🚨 High-Risk Alerts",
            "- **issue-mock-3**: 觸發 Auto-Melt，連續 4 次嘗試修復失敗簽名 `StateContentionError`。",
            "",
            "## 💡 Next Actions",
            "1. 執行 `morning_report.py --push` 將 PR 結算為 GitHub Drafts。",
            "2. 批次核准 8 個 Low Risk 工單，審閱 2 個 Mid/High Risk 異常。",
            "3. 點擊 [Obsidian-Sync] 同步今日夜班產出的 Crystal Lessons 到技能桶。",
        ])
        
        report_text = "\n".join(report)
        self._write_to_kb(report_text, batch_id)
        return report_text

    def push_pr_drafts(self, batch_id: str):
        """將標記為 PR Ready 的任務自動上傳至 GitHub。"""
        print(f"🚀 [MorningReporter] Pushing PR Drafts for {batch_id}...")
        # 💡 使用 subprocess 呼叫 gh pr create --draft --title "Nexus: {goal}"
        # 此處為示意實作
        subprocess.run(["say", "Pushing pull requests to GitHub"], check=False)

    def _write_to_kb(self, content: str, batch_id: str):
        """將報告寫入知識庫的 Morning_Reports 目錄。"""
        log_dir = self.project_root / "logs/morning_reports"
        log_dir.mkdir(parents=True, exist_ok=True)
        report_file = log_dir / f"report_{batch_id}.md"
        report_file.write_text(content, encoding="utf-8")
        print(f"📄 [MorningReporter] Report saved to {report_file}")

    def _voice_notify(self, message: str):
        """觸發語音播報 (修正路徑與調用模式)。"""
        try:
            # 💡 優先使用系統 say 指令，若失敗則回退到 notify.py
            cmd = f"say '{message}'"
            subprocess.run(cmd, shell=True, check=False)
            
            # 同時嘗試執行 notify.py 以維持整合
            notify_script = "/Users/jameschen/.openclaw/skills/audio-notify/scripts/notify.py"
            if Path(notify_script).exists():
                subprocess.run(["python3", notify_script, message], check=False)
        except Exception as e:
            print(f"⚠️ [MorningReporter] Voice notify failed: {e}")

if __name__ == "__main__":
    reporter = MorningReporter(".")
    print(reporter.generate_report("batch-poc-test"))
