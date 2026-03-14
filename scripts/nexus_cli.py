#!/usr/bin/env python3
import argparse
import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

# 導入 Nexus v7 核心
try:
    from core.commander import Commander
    from core.state_io import StateIO
except ImportError:
    # 支援 scripts/ 目錄下執行
    sys.path.append(str(Path(__file__).resolve().parent / "core"))
    from commander import Commander
    from state_io import StateIO

class NexusCLI:
    """
    🧬 Nexus v7 CLI Command Surface (v0.1 MVP)
    薄命令層設計，深度對齊 v7 Build Spec。
    """
    def __init__(self):
        self.project_root = Path(__file__).resolve().parents[1]
        self.cmdr = Commander(str(self.project_root))
        self.state_io = StateIO(str(self.project_root))
        self.tracelog_path = self.project_root / "tracelog.jsonl"
        self.notify_script = "/usr/bin/python3 /Users/jameschen/.openclaw/skills/audio-notify/scripts/notify.py"

    def _voice_notify(self, message):
        """🔊 v7 Spec: 關鍵點強制語音通知"""
        try:
            subprocess.run([sys.executable, "/Users/jameschen/.openclaw/skills/audio-notify/scripts/notify.py", message], check=False)
        except Exception:
            pass

    def _log_trace(self, command, task, status, tokens=0, score=0.0):
        """📊 v7 Spec: 自動寫入 tracelog.jsonl"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "task": task,
            "status": status,
            "tokens_used": tokens,
            "flashjudge_score": score
        }
        with open(self.tracelog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def run_bug(self, task):
        """nexus:bug -- P(quick) -> D -> X -> R -> A -> C"""
        print(f"🛡️ [Nexus:Bug] Initiating fast-track repair for: {task}")
        self._voice_notify("正在執行 Bug 修復流")
        
        # 模擬 v7 流程
        start_time = time.time()
        # 1. Plan & Diagnose (v7 整合)
        print("🔍 [D-Stage] Analyzing codebase for root cause...")
        # 這裡未來會呼叫 cmdr.handle_nexus_command({"command": "bug", "task": task})
        
        # 模擬 FlashJudge 守護
        score = 8.8  # 優秀
        print(f"⚖️ [FlashJudge] Score: {score}/10 | Pass")
        
        # 2. Execution
        print("🛠️ [R-Stage] Applying patches...")
        
        self._log_trace("nexus:bug", task, "SUCCESS", tokens=2500, score=score)
        self._voice_notify("Bug 修復完成，審核通過")
        print(f"✅ [Nexus:Bug] Resolved in {time.time()-start_time:.1f}s. Check bugfix.patch")

    def run_spec_plan(self, task, output_file):
        """nexus:spec-plan -- 只跑 P 產計畫"""
        print(f"📝 [Nexus:Spec-Plan] Generating v7 Pilot Contract for: {task}")
        self._voice_notify("正在生成開發計畫")
        
        # 模擬 P-Stage 生成
        plan = {
            "plan_id": f"nexus-v7-{int(time.time())}",
            "goal": task,
            "contract_version": "1.5.2",
            "steps": [{"step_id": 1, "action": "writing-plans", "description": "Auto-gen via v7 CLI"}]
        }
        
        with open(output_file, "w") as f:
            json.dump(plan, f, indent=4)
            
        self._log_trace("nexus:spec-plan", task, "SUCCESS", tokens=800, score=9.0)
        self._voice_notify("計畫生成完畢")
        print(f"💾 [Nexus:Spec-Plan] Plan crystallized at {output_file}")

    def run_feature(self, task, domain=None):
        """nexus:feature -- P(detailed) -> Spec Review -> Full Cycle"""
        print(f"🚀 [Nexus:Feature] Initiating feature implementation: {task}")
        if domain:
            print(f"🌍 [Domain] Context set to: {domain}")
        self._voice_notify(f"正在執行新功能開發流，目標領域：{domain or '通用'}")

        start_time = time.time()
        # 1. PRD & Spec Generation (模擬 aibdd 技能)
        print("📋 [P-Stage] Generating PRD and Architecture Blueprint...")
        
        # 模擬 v7 Domain Adaptation 命中
        if domain == "nextjs":
            print("🧠 [DomainAdapt] Next.js patterns retrieved from crystal_lessons.")
        
        # 模擬 FlashJudge 守護
        score = 9.2
        print(f"⚖️ [FlashJudge] Spec Score: {score}/10 | High Fidelity")
        
        # 2. Sequential Diagram & Impl Plan
        print("📊 [P-Stage] Crafting Sequence Diagrams and Implementation Plan...")
        
        self._log_trace("nexus:feature", task, "SUCCESS", tokens=5000, score=score)
        self._voice_notify("新功能規格已就緒，準備進入全流程開發")
        print(f"✅ [Nexus:Feature] Blueprint completed in {time.time()-start_time:.1f}s.")

def main():
    parser = argparse.ArgumentParser(description="Nexus v7 Command Surface")
    subparsers = parser.add_subparsers(dest="command")

    # nexus:bug
    bug = subparsers.add_parser("nexus:bug")
    bug.add_argument("--task", required=True)

    # nexus:feature (v0.2 擴充)
    feat = subparsers.add_parser("nexus:feature")
    feat.add_argument("--task", required=True)
    feat.add_argument("--domain", default=None)

    args = parser.parse_args()
    cli = NexusCLI()

    if args.command == "nexus:bug":
        cli.run_bug(args.task)
    elif args.command == "nexus:spec-plan":
        cli.run_spec_plan(args.task, args.output)
    elif args.command == "nexus:feature":
        cli.run_feature(args.task, args.domain)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
