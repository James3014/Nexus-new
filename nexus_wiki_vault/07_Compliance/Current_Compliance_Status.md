---
title: Current Compliance Status
type: compliance
status: active
version_scope: v22.5
owner: agent
confidence: high
last_compiled: 2026-04-17
source_of_truth: 07_Compliance/Compliance_Dashboard.md
tags:
  - compliance
  - status
  - governance
---

# 🛡️ Compliance Status: Nexus Enterprise v22.5
- **Timestamp**: 2026-04-17 23:03:04
- **Commit SHA**: `d11aaff8d8cd10234dbfec74e2d5a6a012796cce`
- **Nexus Participation Ratio**: 85.0%

## 🔍 Core Audit Dimensions (SOC2-like)
| Dimension | Status | Metrics |
|-----------|--------|---------|
| Isolation | ✅ PASS | leakage: 0.0 |
| Hallucination | ✅ PASS | rate: 0.0 |
| Concurrency | ✅ PASS | p95_latency: 3.9352214392994775, recall: 0.98 |
| Security | ✅ PASS | audit_trail: PRESENT |
| Integration | ✅ PASS | latency: 2.3 |

## 🧱 Gate Summary
- **acceptance_check**: PASS
- **contract_check**: PASS
- **ci_gate_full_dry_run**: PASS

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
- [ ] 是否將 85.0% 的參與比率定義為門檻前提還是告警閾值？

**[Source: 07_Compliance/Compliance_Dashboard.md]**

[[System Overview]]
