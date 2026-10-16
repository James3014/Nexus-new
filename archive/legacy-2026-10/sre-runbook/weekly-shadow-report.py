#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime
import pandas as pd

def generate_weekly_report():
    # 🛡️ 1. Paths
    repo_root = Path(__file__).resolve().parents[1]
    cal_path = repo_root / ".nexus/shadow/calibration.json"
    runs_path = repo_root / ".nexus/shadow/runs"
    
    print(f"🛡️ Generating Weekly Shadow Audit Report (v22/v24 Spec)...")

    # 🛡️ 2. Load Calibration Data
    if not cal_path.exists():
        print(f"⚠️  Calibration data not found at {cal_path}")
        return
    
    with open(cal_path, "r") as f:
        cal = json.load(f)

    # 🛡️ 3. Load Run Data
    runs = []
    if runs_path.exists():
        for run_file in runs_path.glob("*.json"):
            try:
                with open(run_file, "r") as f:
                    data = json.load(f)
                    runs.append({
                        "id": run_file.stem,
                        "pr": data.get("pr_number"),
                        "status": data.get("status", "UNKNOWN"),
                        "latency_ms": data.get("latency_ms", 0),
                        "mode": data.get("mode", "unknown"),
                        "timestamp": data.get("timestamp", datetime.now().isoformat())
                    })
            except Exception as e:
                print(f"❌ Failed to read {run_file}: {e}")

    if not runs:
        print("⚠️  No run data found in .nexus/shadow/runs/")
        # Mock data if empty for demo/test
        runs = [{"id": "dummy", "pr": 0, "status": "BOOT", "latency_ms": 100, "mode": "mock", "timestamp": datetime.now().isoformat()}]

    # 🛡️ 4. Analytics
    df = pd.DataFrame(runs)
    
    report = {
        "report_id": f"shadow-{datetime.now().strftime('%Y%m%d-%H%M')}",
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_audits": len(runs),
            "healthy_count": len(df[df["status"] == "HEALTHY"]),
            "degraded_count": len(df[df["mode"] == "degraded"]),
            "avg_latency_ms": float(df["latency_ms"].mean()),
            "p95_latency_ms": float(df["latency_ms"].quantile(0.95)),
            "false_positive_rate": cal.get("false_positive_rate", 0),
            "whitelist_size": len(cal.get("whitelist", []))
        },
        "governance_status": cal.get("status", "UNKNOWN")
    }

    # 🛡️ 5. Output
    report_dir = repo_root / "sre-runbook/reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = report_dir / f"{report['report_id']}.json"
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    
    print(f"✅ Weekly Shadow Report generated: {output_path}")
    return report

if __name__ == "__main__":
    generate_weekly_report()
