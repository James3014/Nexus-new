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
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run_scheduler(self) -> int:
        report_path = self.repo_root / ".nexus/reports/learn/scheduler_last_run.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        results = {"steps": {}}
        try:
            res_policy = subprocess.run(
                ["uv", "run", "scripts/engine/nexus_cli.py", "nexus", "learn:phase-policy", "--output-json"], 
                capture_output=True, text=True, cwd=self.repo_root
            )
            if res_policy.returncode == 0:
                policy_data = json.loads(res_policy.stdout)
                readiness = policy_data.get("slo_readiness", 0.0)
                results["slo_readiness"] = readiness
                if readiness < 0.5:
                    dispatch_alert("DEGRADED", f"Low SLO readiness: {readiness:.1%}", policy_data)
                    return 2
                return 0
            dispatch_alert("FAILED", "Policy check failed")
            return 3
        except Exception as e:
            dispatch_alert("FAILED", f"Error: {e}")
            return 3
        finally:
            results["timestamp"] = datetime.now(timezone.utc).isoformat()
            results["exit_code"] = 0 
            report_path.write_text(json.dumps(results, indent=2))
