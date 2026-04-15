import os, json, sys, subprocess, time
from pathlib import Path
from datetime import datetime, timezone
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))
from scripts.ops.learn_alert_dispatcher import dispatch_alert

def run_scheduler():
    report_path = repo_root / ".nexus/reports/learn/scheduler_last_run.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    results = {"steps": {}}
    try:
        res_policy = subprocess.run(["uv", "run", "scripts/engine/nexus_cli.py", "nexus", "learn:phase-policy", "--output-json"], capture_output=True, text=True, cwd=repo_root)
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
        results["exit_code"] = 0 # simplified for trace
        report_path.write_text(json.dumps(results, indent=2))

if __name__ == "__main__":
    sys.exit(run_scheduler())
