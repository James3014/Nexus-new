#!/usr/bin/env python3
import os
import json
from datetime import datetime
from pathlib import Path

# 🛡️ Nexus Wiki Changelog Autodraft (Agent S - v1.0)
# [NEXUS IDENTITY: a670624 + CI-GUARDED]

REPO_ROOT = Path("/Users/jameschen/Workspace/nexus")
REPORT_DIR = REPO_ROOT / ".nexus" / "reports"
SNAPSHOT_PATH = REPORT_DIR / "wiki_slo_snapshot.json"
HISTORY_PATH = REPORT_DIR / "wiki_slo_history.jsonl"
DRAFT_PATH = REPORT_DIR / "wiki_changelog_draft.md"

def load_history():
    if not HISTORY_PATH.exists(): return []
    try:
        with open(HISTORY_PATH, "r") as f:
            return [json.loads(line) for line in f.readlines()]
    except: return []

def generate_draft():
    print("🛡️ WS-S: Generating Changelog Autodraft...")
    history = load_history()
    if len(history) < 2:
        print("Not enough history to generate delta. Generating static draft.")
        curr = history[-1] if history else {}
        prev = {}
    else:
        curr = history[-1]
        prev = history[-2]

    # Delta Calculation
    cov_delta = curr.get("coverage", {}).get("global", 0) - prev.get("coverage", {}).get("global", 0)
    p0_delta = curr.get("drift", {}).get("p0", 0) - prev.get("drift", {}).get("p0", 0)
    mismatch_delta = curr.get("truth", {}).get("mismatch", 0) - prev.get("truth", {}).get("mismatch", 0)

    draft_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    md = f"""# [Governance Autodraft] Wiki Evolution Summary

**Draft Timestamp**: {draft_time}
**Base Comparison**: {prev.get('timestamp', 'N/A')} -> {curr.get('timestamp', 'N/A')}

## 📊 Governance Delta (↑↓)

- **Global Coverage**: {curr['coverage']['global']:.2f}% (Delta: {cov_delta:+.2f}%)
- **P0 Drifts**: {curr['drift']['p0']} (Delta: {p0_delta:+d})
- **Truth Mismatches**: {curr['truth']['mismatch']} (Delta: {mismatch_delta:+d})

## 📝 Suggested Entry Text (Ops - Governance Changelog.md)

| Date | Change (項) | Affected Components | Risk | Rollback Plan | Verifier |
|---|---|---|---|---|---|
| {datetime.now().strftime("%Y-%m-%d")} | **Auto-Hardening Cycle** | Wiki Vault, CI Reports | Low | Git revert | Antigravity (Agent S) |

> **Audit Summary**: Coverage {curr['coverage']['global']:.1f}% / P0={curr['drift']['p0']} / Mismatch={curr['truth']['mismatch']}.

## ⚠️ Notable Regressions
"""
    if cov_delta < -0.1: md += f"- **Coverage Drop**: Global coverage decreased by {abs(cov_delta):.2f}%.\n"
    if p0_delta > 0: md += f"- **P0 DRIFT**: {p0_delta} new P0 drifts detected! [Source: wiki_drift_report.json]\n"
    if mismatch_delta > 0: md += f"- **TRUTH MISMATCH**: {mismatch_delta} new logical truth mismatches!\n"
    if not any([cov_delta < -0.1, p0_delta > 0, mismatch_delta > 0]):
        md += "- **No major regressions detected.** 🟢\n"

    with open(DRAFT_PATH, "w") as f:
        f.write(md)
    print(f"📝 Changelog draft saved to {DRAFT_PATH}")

if __name__ == "__main__":
    generate_draft()
