---
last_compiled: 2026-04-06
status: active
tags:
- governance
- slo
- dashboard
- tracking
title: Ops - Governance SLO Dashboard
type: ops
---



# Ops - Governance SLO Dashboard

## One-sentence summary
本頁即時呈現 Nexus 治理層 SLO 指標與近期趨勢，作為發版前健康度總覽。 [Source: scripts/ops/wiki_slo_dashboard.py]

## Role / responsibility
- 聚合 `drift/coverage/truth` 報表，提供治理儀表板。
- 讓人類審核與 [[CD Promotion Gate|CI gate]] 共用同一組 SLO 觀測基線。

## Matrix / flow / interfaces
| Metric | Source Report | Gate Meaning |
|---|---|---|
| `p0_count` | `.nexus/reports/wiki_drift_report.json` | `>0` 代表阻斷級風險 |
| `global_coverage_pct` | `.nexus/reports/wiki_coverage_report.json` | 低於門檻需補映射 |
| `keypath_coverage_pct` | `.nexus/reports/wiki_keypath_coverage_report.json` | 關鍵路徑需 100% |
| `weighted_score` | `.nexus/reports/wiki_capability_coverage_report.json` | 權重覆蓋率需 >90% |
| `pass_rate` | `.nexus/reports/wiki_eval_report.json` | 回歸測試通過率需 >95% |
| `mismatch_count` | `.nexus/reports/wiki_truth_claims_report.json` | `>0` 代表真值不一致 |

## 🎯 Current Status (Latest Snapshot)

| Metric | Value | Status |
| :--- | :--- | :--- |
| **P0 Drift** | 0 | ✅ PASS |
| **Weighted Coverage** | 0.00% | ⚠️ LOW |
| **Eval Pass Rate** | 0.00% | ❌ FAIL |
| **Evidence Rate** | 0.00% | ❌ FAIL |
| **Stale Pages** | 0 | ✅ FRESH |
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
- [ ] 是否將 `link_audit` / `owner_audit` 併入 release hard gate。---
aliases: '[Drift Audit, Wiki Drift, Stale [[documentation|Documentation]] Check]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: scripts/ops/wiki_drift_audit.py
status: active
tags: '[ops, audit, drift, maintenance]'
title: Ops - Wiki Drift Audit
type: ops
version_scope: '[v17.1, v22, v23]'
---



# Ops - Wiki Drift Audit

## One-sentence summary
本頁解釋 Nexus Wiki 的「路徑脫節與時效漂移」自動審計機制。 [Source: scripts/ops/wiki_drift_audit.py]

## Role / responsibility
- **物理存在校驗**: 自動檢測 Wiki 內所有 `[Source: 00_Home/System Overview.md]` 提及的路徑在 Repo 中是否依然存在。 [Source: scripts/ops/wiki_drift_audit.py]
- **內容時效監控 (Stale Detection)**: 對比 Wiki 頁面的最後修改時間與其引用之程式檔案的 Git 最後提交時間。 [Source: scripts/ops/wiki_drift_audit.py]

## Drift Audit Mechanism (審計機制)

### 1. 物理掃描 (Physical Path Check)
- **邏輯**: 提取全庫 `[Source: 00_Home/System Overview.md]` 標籤 -> 對比 `PROJECT_ROOT` -> 若路徑不存在則記錄為 `Missing Claim`。
- **CI 整合**: 整合於 `ci_gate.py` 之 `Wiki Drift Audit` 步驟。 [Source: scripts/ops/ci_gate.py]

## Upstream
- **Wiki Audit Engine**: `scripts/ops/wiki_drift_audit.py` [Code: scripts/ops/wiki_drift_audit.py]

## Downstream
- **[[Ops - Governance Changelog]]**: 記錄漂移修復的歷史。

## Related modules / files
- `scripts/ops/wiki_drift_audit.py`: 漂移審計核心。 [Source: scripts/ops/wiki_drift_audit.py]

## Source notes
- v22 Engine Spec: 要求治理文檔必須具備「物理可對位性」與「時效一致性」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Hard Fail**: 何時將 Wiki Drift Audit 升級為 Hard Fail。

---
[[System Overview]]
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