from __future__ import annotations
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class LearnRefreshService:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.status_file = self.repo_root / ".nexus" / "learn_refresh_daemon_status.json"
        self.venv_python = self.repo_root / ".venv" / "bin" / "python"
        
    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def run_cmd(self, args: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(args, cwd=self.repo_root, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def write_status(self, payload: dict[str, Any]) -> None:
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def run_refresh_loop(self, topic: str, interval_sec: int, due_within_days: int, pass_threshold: float, question_count: int, benchmark_manifest: str = None):
        logging.info("🚀 Starting Learn Refresh Loop (topic=%s, interval=%ds)", topic, interval_sec)
        while True:
            try:
                self._execute_refresh_cycle(topic, due_within_days, pass_threshold, question_count, benchmark_manifest)
            except Exception as e:
                logging.error("❌ Loop error: %s", e)
            
            if interval_sec <= 0: break
            time.sleep(interval_sec)

    def _execute_refresh_cycle(self, topic, due_within_days, pass_threshold, question_count, benchmark_manifest):
        status = {"last_run": self.now_iso(), "steps": {}}
        
        # 1. Plan
        plan_report = self.repo_root / ".nexus/reports/learn/daemon_refresh_plan.json"
        plan_cmd = [str(self.venv_python), "scripts/engine/nexus_cli.py", "nexus", "learn:refresh-plan", 
                    "--due-within-days", str(due_within_days), "--report-file", str(plan_report.relative_to(self.repo_root)), "--output-json"]
        if topic: plan_cmd.extend(["--topic", topic])
        
        rc, out, err = self.run_cmd(plan_cmd)
        status["steps"]["plan"] = {"ok": rc == 0, "output": out[:500]}
        
        # 2. Refresh (if items due)
        refresh_report = self.repo_root / ".nexus/reports/learn/daemon_refresh_run.json"
        refresh_cmd = [str(self.venv_python), "scripts/engine/nexus_cli.py", "nexus", "learn:refresh", 
                       "--due-only", "--pass-threshold", str(pass_threshold), "--question-count", str(question_count),
                       "--report-file", str(refresh_report.relative_to(self.repo_root)), "--output-json"]
        if topic: refresh_cmd.extend(["--topic", topic])
        
        rc, out, err = self.run_cmd(refresh_cmd)
        status["steps"]["refresh"] = {"ok": rc == 0, "output": out[:500]}
        
        self.write_status(status)
        logging.info("✅ Refresh cycle completed at %s", status["last_run"])
