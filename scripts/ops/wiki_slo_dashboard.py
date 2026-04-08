#!/usr/bin/env python3
import os
import json
from datetime import datetime
from pathlib import Path

# 🛡️ Nexus Governance SLO Dashboard (Agent R - v1.0)
# [NEXUS IDENTITY: a670624 + CI-GUARDED]

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
REPORT_DIR = REPO_ROOT / ".nexus" / "reports"
SNAPSHOT_PATH = REPORT_DIR / "wiki_slo_snapshot.json"
HISTORY_PATH = REPORT_DIR / "wiki_slo_history.jsonl"
DASHBOARD_MD = REPO_ROOT / "nexus_wiki_vault" / "06_Ops" / "Ops - Governance SLO Dashboard.md"

def load_json(path):
    if not path.exists(): return {}
    try:
        with open(path, "r") as f: return json.load(f)
    except: return {}

def generate_slo():
    print("🛡️ WS-R: Generating Governance SLO Dashboard...")
    
    # 1. Load component reports
    drift = load_json(REPORT_DIR / "wiki_drift_report.json")
    coverage = load_json(REPORT_DIR / "wiki_coverage_report.json")
    truth = load_json(REPORT_DIR / "wiki_truth_claims_report.json")
    
    # 2. Extract Linter status from drift or direct execution
    linter_failed = 0
    try:
        import subprocess
        res = subprocess.run("uv run scripts/ops/wiki_linter.py --strict", shell=True, capture_output=True, text=True, cwd=REPO_ROOT)
        # Parse: Summary: 50 Passed, 4 Failed, 1 Waived
        match = re.search(r"(\d+)\s+Failed", res.stdout)
        if match: linter_failed = int(match.group(1))
    except:
        pass
    
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "drift": {
            "p0": drift.get("summary", {}).get("p0_count", 0),
            "p1": drift.get("summary", {}).get("p1_count", 0),
            "p2": drift.get("summary", {}).get("p2_count", 0),
            "total": drift.get("summary", {}).get("total_drifts", 0)
        },
        "coverage": {
            "global": coverage.get("global_coverage", 0.0),
            "keypath": coverage.get("keypath_coverage", 0.0)
        },
        "truth": {
            "mismatch": truth.get("summary", {}).get("mismatch_count", 0),
            "infra_error": truth.get("summary", {}).get("infra_error_count", 0),
            "policy_violation": truth.get("summary", {}).get("policy_violation_count", 0)
        },
        "linter": {
            "failed": linter_failed
        }
    }
    
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2)
        
    with open(HISTORY_PATH, "a") as f:
        f.write(json.dumps(snapshot) + "\n")
        
    print(f"📊 SLO Snapshot saved to {SNAPSHOT_PATH}")
    
    # 2. Update Wiki Dashboard (Simple Template)
    history_lines = []
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r") as f:
            history_lines = f.readlines()
            
    recent_10 = [json.loads(line) for line in history_lines[-10:]]
    recent_10.reverse()
    
    md_content = f"""---
title: Ops - Governance SLO Dashboard
type: ops
status: active
tags: [governance, slo, dashboard, tracking]
last_compiled: {datetime.now().strftime("%Y-%m-%d")}
---

# Ops - Governance SLO Dashboard

本頁即時呈現 Nexus 治理層的服務標準協議 (SLO) 指標與長期趨勢。 [Source: scripts/ops/wiki_slo_dashboard.py]

## 🎯 Current Status (Latest Snapshot)

| Metric | Value | Status |
| :--- | :--- | :--- |
| **P0 Drift** | {snapshot['drift']['p0']} | {"✅ PASS" if snapshot['drift']['p0'] == 0 else "❌ BLOCK"} |
| **Global Coverage** | {snapshot['coverage']['global']:.2f}% | {"✅ OK" if snapshot['coverage']['global'] >= 85.0 else "⚠️ LOW"} |
| **Key Path Coverage** | {snapshot['coverage']['keypath']:.2f}% | {"✅ 100%" if snapshot['coverage']['keypath'] == 100.0 else "❌ FAIL"} |
| **Truth Mismatch** | {snapshot['truth']['mismatch']} | {"✅ MATCH" if snapshot['truth']['mismatch'] == 0 else "❌ MISMATCH"} |

## 📈 Long-term Trends (Last 10 Runs)

| Timestamp | P0 | P1/P2 | Global Cov | KeyPath Cov | Truth Mismatch |
| :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for item in recent_10:
        ts = item['timestamp'][:16].replace("T", " ")
        md_content += f"| {ts} | {item['drift']['p0']} | {item['drift']['p1']}/{item['drift']['p2']} | {item['coverage']['global']:.1f}% | {item['coverage']['keypath']:.1f}% | {item['truth']['mismatch']} |\n"

    md_content += "\n## Upstream\n- **Governance Audit Scripts**: 提供原始數據。 [[System Overview]]\n"
    
    with open(DASHBOARD_MD, "w") as f:
        f.write(md_content)
    
    print(f"📝 Dashboard Wiki updated: {DASHBOARD_MD}")

if __name__ == "__main__":
    generate_slo()
