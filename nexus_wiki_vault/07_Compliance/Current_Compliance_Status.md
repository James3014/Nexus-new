---
title: Current Compliance Status
type: compliance
status: active
version_scope: v22.5
owner: agent
confidence: low
last_compiled: 2026-10-12
source_of_truth: 07_Compliance/Compliance_Dashboard.md
tags:
  - compliance
  - status
  - governance
---

# 🛡️ Compliance Status: Nexus Enterprise v22.5
- **Timestamp**: 2026-10-12 05:07:52
- **Commit SHA**: `3360668ca10d5a0159416ab4ee5a7fe3eaface27`
- **Report Status**: SIMULATED (semantic: UNVERIFIED; simulated: True)
- **Nexus Participation Ratio**: NOT_MEASURED

## 🔍 Core Audit Dimensions (SOC2-like)
| Dimension | Status | Metrics |
|-----------|--------|---------|
| Isolation | ⚠️ SIMULATED (not measured) | simulated: True, would_pass: True, leakage: 0.0 |
| Hallucination | ⚠️ SIMULATED (not measured) | simulated: True, would_pass: True, rate: 0.005 |
| Concurrency | ⚠️ SIMULATED (not measured) | simulated: True, would_pass: True, p95_latency: 4.048979591836735, recall: 0.98 |
| Security | ⚠️ SIMULATED (not measured) | simulated: True, would_pass: True, audit_trail: PRESENT |
| Integration | ⚠️ SIMULATED (not measured) | simulated: True, would_pass: True, latency: 2.3 |

## 🧱 Gate Summary
- **acceptance_check**: NOT_RUN
- **contract_check**: NOT_RUN
- **ci_gate_full_dry_run**: NOT_RUN

## One-sentence summary
本頁彙整最新合規交付狀態與關鍵門禁結果，作為治理決策的即時快照。 [Source: 07_Compliance/Compliance_Dashboard.md]

## Role / responsibility
- 提供主要治理狀態可讀視圖，供運維與交付決策使用。 [Source: 07_Compliance/Compliance_Dashboard.md]
- 協助識別偏離目標的指標並向關聯流程回推。 [Source: scripts/ops/ci_gate.py]

## Upstream
- **Compliance Dashboard**: 指標來源總彙整。 [Source: 07_Compliance/Compliance_Dashboard.md]
- **Wiki Linter**: 對文件與治理流程的規範檢核。 [Source: scripts/ops/wiki_linter.py]

## Downstream
- **[06_Ops/Ops - SLO Dashboard](../06_Ops/Ops - Governance SLO Dashboard.md)**: 對外展示治理趨勢。 [Source: 06_Ops/Ops - Governance SLO Dashboard.md]
- **[07_Compliance/Incident_Trace_Log](Incident_Trace_Log.md)**: 將失敗樣本持續跟蹤。 [Source: 07_Compliance/Incident_Trace_Log.md]

## Related modules / files
- `07_Compliance/Compliance_Dashboard.md`
- `06_Ops/Ops - Governance Changelog.md`
- `scripts/ops/ci_gate.py`

## Source notes
- 本頁與 CI Gate 報表結果保持一致。 [Source: scripts/ops/ci_gate.py]

## Open questions / conflicts
- [ ] Nexus 參與比率目前為 NOT_MEASURED（企業審計為 SIMULATED，未實測）；待真實量測後再定義門檻前提或告警閾值。

**[Source: 07_Compliance/Compliance_Dashboard.md]**

[[System Overview]]
