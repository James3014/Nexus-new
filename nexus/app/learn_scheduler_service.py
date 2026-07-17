from __future__ import annotations
import os
import json
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone
from scripts.ops.learn_alert_dispatcher import dispatch_alert

class LearnSchedulerService:
    def __init__(self, repo_root: Path, *, report_root: Path | None = None):
        self.repo_root = repo_root
        self.report_root = report_root or repo_root

    def run_scheduler(self) -> int:
        report_path = self.report_root / ".nexus/reports/learn/scheduler_last_run.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "scripts/engine/nexus_cli.py",
            "nexus",
            "learn:phase-policy",
            "--output-json",
        ]
        results = {"steps": {}, "policy_command": command}
        exit_code = 3
        try:
            res_policy = subprocess.run(
                command,
                capture_output=True, text=True, cwd=self.repo_root
            )
            results["steps"]["policy"] = {
                "returncode": int(res_policy.returncode),
                "stderr": str(res_policy.stderr or "")[-1000:],
            }
            if res_policy.returncode == 0:
                policy_data = json.loads(res_policy.stdout)
                readiness = policy_data.get("slo_readiness", 0.0)
                results["slo_readiness"] = readiness
                results["policy"] = policy_data.get("policy", {})
                if readiness < 0.5:
                    dispatch_alert("DEGRADED", f"Low SLO readiness: {readiness:.1%}", policy_data)
                    results["alert_dispatched"] = True
                    exit_code = 2
                else:
                    results["alert_dispatched"] = False
                    exit_code = 0
            else:
                dispatch_alert("FAILED", "Policy check failed")
                results["alert_dispatched"] = True
        except Exception as e:
            dispatch_alert("FAILED", f"Error: {e}")
            results["alert_dispatched"] = True
            results["error"] = str(e)[:1000]
        finally:
            results["timestamp"] = datetime.now(timezone.utc).isoformat()
            results["exit_code"] = exit_code
            report_path.write_text(json.dumps(results, indent=2))
        return exit_code
