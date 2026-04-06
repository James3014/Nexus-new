---
title: Ops - Governance SLO Dashboard
type: ops
status: active
tags: [governance, slo, dashboard, tracking]
last_compiled: 2026-04-06
---

# Ops - Governance SLO Dashboard

## One-sentence summary
本頁即時呈現 Nexus 治理層 SLO 指標與近期趨勢，作為發版前健康度總覽。 [Source: scripts/ops/wiki_slo_dashboard.py]

## Role / responsibility
- 聚合 `drift/coverage/truth` 報表，提供治理儀表板。
- 讓人類審核與 CI gate 共用同一組 SLO 觀測基線。

## Matrix / flow / interfaces
| Metric | Source Report | Gate Meaning |
|---|---|---|
| `p0_count` | `.nexus/reports/wiki_drift_report.json` | `>0` 代表阻斷級風險 |
| `global_coverage_pct` | `.nexus/reports/wiki_coverage_report.json` | 低於門檻需補映射 |
| `keypath_coverage_pct` | `.nexus/reports/wiki_keypath_coverage_report.json` | 關鍵路徑需 100% |
| `mismatch_count` | `.nexus/reports/wiki_truth_claims_report.json` | `>0` 代表真值不一致 |

## 🎯 Current Status (Latest Snapshot)

| Metric | Value | Status |
| :--- | :--- | :--- |
| **P0 Drift** | 0 | ✅ PASS |
| **Global Coverage** | 0.00% | ⚠️ LOW |
| **Key Path Coverage** | 0.00% | ❌ FAIL |
| **Truth Mismatch** | 4 | ❌ MISMATCH |

## 📈 Long-term Trends (Last 10 Runs)

| Timestamp | P0 | P1/P2 | Global Cov | KeyPath Cov | Truth Mismatch |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-04-06 09:17 | 0 | 11/0 | 0.0% | 0.0% | 4 |
| 2026-04-06 09:17 | 0 | 11/0 | 0.0% | 0.0% | 4 |
| 2026-04-06 09:17 | 0 | 11/0 | 0.0% | 0.0% | 0 |
| 2026-04-06 09:17 | 0 | 11/0 | 0.0% | 0.0% | 0 |
| 2026-04-06 09:14 | 0 | 11/0 | 0.0% | 0.0% | 0 |

## Upstream
- `scripts/ops/wiki_slo_dashboard.py` 產出快照與趨勢。 [Code: scripts/ops/wiki_slo_dashboard.py]
- [[System Overview]]

## Downstream
- 作為 `ci_gate.py` 前置人工判讀面板。
- 提供治理週期回顧與問題分流依據。

## Related modules / files
- `scripts/ops/wiki_slo_dashboard.py`
- `.nexus/reports/wiki_slo_snapshot.json`
- `.nexus/reports/wiki_slo_history.jsonl`

## Source notes
- 數值來自最新報表，不應手工改寫。

## Open questions / conflicts
- [ ] 是否將 `global_coverage_pct` 低門檻升級為 hard gate。
- [ ] 是否將 `link_audit` / `owner_audit` 併入 release hard gate。
