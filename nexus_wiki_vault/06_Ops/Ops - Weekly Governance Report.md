---
last_compiled: 2026-04-06
owner: agent
status: active
tags:
- governance
- report
- weekly
title: Ops - Weekly Governance Report
type: ops
---



# Ops - Weekly Governance Report (2026-04-06)

## One-sentence summary
本報告聚合 Nexus Wiki 治理指標與趨勢，提供每週健康度總覽與風險評估。

## Role / responsibility
- 聚合多方報表，提供單一治理視角。
- 協助 Agent 與人類決策者識別治理缺口。

## Executive Summary
Generated at: 2026-04-06 10:27

| Metric | Status | Value |
| :--- | :--- | :--- |
| **P0 Drift** | ✅ PASS | 0 |
| **Weighted Coverage** | ✅ PASS | 100.00% |
| **Stale Pages** | ✅ FRESH | 0 |
| **Eval Pass Rate** | ✅ PASS | 100.00% |
| **Evidence Rate** | ⚠️ WEAK | 75.00% |

## Upstream
- [[System Overview]]
- `.nexus/reports/` 中的各項 JSON 原始報表。

## Downstream
- 作為 [[CD Promotion Gate|CI gate]] 的治理依據。
- [[Ops - Governance SLO Dashboard]]

## Risks (Top 5)
✅ No high-priority risks detected.

## Trend Snapshot
- **Writeback Activity**: 0 received, 0 written to wiki.

## Action Queue
1. [ ] Continue routine monitoring.
2. [ ] Explore further coverage expansion for discovery modules.

## Related modules / files
- `scripts/ops/wiki_weekly_governance_report.py`
- `scripts/ops/wiki_linter.py`

## Source notes
- 自動生成於 per-run CI cycle。
[Source: scripts/ops/wiki_weekly_governance_report.py]

## Open questions / conflicts
- [ ] 是否需要將此報告發送至 Slack/Email。