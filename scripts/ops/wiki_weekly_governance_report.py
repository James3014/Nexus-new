#!/usr/bin/env python3
import os
import json
import datetime
from pathlib import Path

# 🛡️ Nexus Wiki Weekly Governance Report Generator v1.1
# Purpose: Aggregate all Wiki governance metrics into a single human-readable weekly report.

REPO_ROOT = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
REPORT_DIR = REPO_ROOT / ".nexus" / "reports"
OUTPUT_PATH = REPO_ROOT / "nexus_wiki_vault" / "06_Ops" / "Ops - Weekly Governance Report.md"

def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception as e:
            print(f"⚠️ Error loading {path}: {e}")
    return None

def generate_report():
    drift = load_json(REPORT_DIR / "wiki_drift_report.json")
    capability = load_json(REPORT_DIR / "wiki_capability_coverage_report.json")
    eval_reg = load_json(REPORT_DIR / "wiki_eval_report.json")
    writeback = load_json(REPORT_DIR / "wiki_writeback_report.json")
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    report = f"""---
title: Ops - Weekly Governance Report
type: ops
status: active
tags: [governance, report, weekly]
last_compiled: {date_str}
owner: agent
---

# Ops - Weekly Governance Report ({date_str})

## One-sentence summary
本報告聚合 Nexus Wiki 治理指標與趨勢，提供每週健康度總覽與風險評估。

## Role / responsibility
- 聚合多方報表，提供單一治理視角。
- 協助 Agent 與人類決策者識別治理缺口。

## Executive Summary
Generated at: {today_str}

| Metric | Status | Value |
| :--- | :--- | :--- |
"""

    # Drift Status
    if drift:
        p0 = drift["summary"]["p0_count"]
        status = "✅ PASS" if p0 == 0 else "❌ BLOCK"
        report += f"| **P0 Drift** | {status} | {p0} |\n"
    else:
        report += f"| **P0 Drift** | ⚠️ N/A | Missing Report |\n"
        
    # Capability Status
    if capability:
        weighted = capability["summary"]["weighted_score"]
        status = "✅ PASS" if weighted >= 0.95 else "⚠️ WARN" if weighted >= 0.85 else "❌ FAIL"
        report += f"| **Weighted Coverage** | {status} | {weighted:.2%} |\n"
        
        stale = capability["summary"]["stale_count"]
        status = "✅ FRESH" if stale == 0 else "⚠️ AGING"
        report += f"| **Stale Pages** | {status} | {stale} |\n"
    else:
        report += f"| **Weighted Coverage** | ⚠️ N/A | Missing Report |\n"

    # Eval Status
    if eval_reg:
        pass_rate = eval_reg["summary"]["pass_rate"]
        status = "✅ PASS" if pass_rate >= 0.90 else "❌ FAIL"
        report += f"| **Eval Pass Rate** | {status} | {pass_rate:.2%} |\n"
        
        evidence_rate = eval_reg["summary"].get("evidence_pass_rate", 0.0)
        status = "✅ PASS" if evidence_rate >= 0.85 else "⚠️ WEAK"
        report += f"| **Evidence Rate** | {status} | {evidence_rate:.2%} |\n"
    else:
        report += f"| **Eval Pass Rate** | ⚠️ N/A | Missing Report |\n"

    report += "\n## Upstream\n"
    report += "- [[System Overview]]\n"
    report += "- `.nexus/reports/` 中的各項 JSON 原始報表。\n"

    report += "\n## Downstream\n"
    report += "- 作為 CI gate 的治理依據。\n"
    report += "- [[Ops - Governance SLO Dashboard]]\n"

    report += "\n## Risks (Top 5)\n"
    risks = []
    
    if drift and drift["summary"]["p0_count"] > 0:
        risks.append(f"- [P0] {drift['summary']['p0_count']} critical drift detections in {drift['summary']['total_drift_count']} total.")
    
    if capability:
        if capability["summary"]["stale_count"] > 5:
            risks.append(f"- [HIGH] Knowledge aging: {capability['summary']['stale_count']} pages are past the 45-day freshness threshold.")
        if capability["summary"]["ownership_missing_count"] > 0:
            risks.append(f"- [MED] Orphaned pages: {capability['summary']['ownership_missing_count']} pages missing 'owner' frontmatter.")
            
    if eval_reg and eval_reg["summary"]["failed_count"] > 0:
        risks.append(f"- [HIGH] Regression failure: {eval_reg['summary']['failed_count']} governance questions failed keyword verification.")

    if not risks:
        report += "✅ No high-priority risks detected.\n"
    else:
        for risk in risks[:5]:
            report += risk + "\n"

    report += "\n## Trend Snapshot\n"
    if writeback:
        wb_summary = writeback.get("summary", {})
        report += f"- **Writeback Activity**: {wb_summary.get('received', 0)} received, {wb_summary.get('written', 0)} written to wiki.\n"
    
    report += "\n## Action Queue\n"
    if risks:
        report += "1. [ ] Resolve P0 drift items immediately.\n"
        report += "2. [ ] Update stale wiki pages and assign owners.\n"
        report += "3. [ ] Investigate and fix failed regression cases.\n"
    else:
        report += "1. [ ] Continue routine monitoring.\n"
        report += "2. [ ] Explore further coverage expansion for discovery modules.\n"

    report += "\n## Related modules / files\n"
    report += "- `scripts/ops/wiki_weekly_governance_report.py`\n"
    report += "- `scripts/ops/wiki_linter.py`\n"

    report += "\n## Source notes\n"
    report += "- 自動生成於 per-run CI cycle。\n"
    report += "[Source: scripts/ops/wiki_weekly_governance_report.py]\n"

    report += "\n## Open questions / conflicts\n"
    report += "- [ ] 是否需要將此報告發送至 Slack/Email。\n"
    
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report)
    print(f"✅ Weekly Governance Report generated at: {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_report()
