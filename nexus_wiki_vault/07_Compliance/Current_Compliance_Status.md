---
title: "Current Compliance Status"
aliases: "Compliance Status"
confidence: high
last_compiled: "2026-04-08"
owner: agent
source_of_truth: "scripts/ops/compliance_to_wiki.py"
status: active
tags: "[compliance, audit, nexus]"
type: report
version_scope: "[v22.5]"
---

# 🛡️ Compliance Status: Nexus Enterprise v22.5

## One-sentence summary
本頁面記錄 Nexus 系統的合規性指標，包含隔離性、幻覺率及安全性審核結果。

## Role / responsibility
- **監控**: 追蹤系統是否符合 SOC2/FedRAMP 等級的安全標準。
- **存證**: 作為 Nexus 參與率與門檻校驗的權威數據來源。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 總體治理入口。
- `scripts/ops/compliance_to_wiki.py` (數據生成器)

## Downstream
- [[07_Compliance/Compliance_Dashboard]]
- [[06_Ops/Ops - Governance SLO Dashboard]]

## Related modules / files
- [[06_Ops/Ops - Truth Claims Register]]
- [[07_Compliance/Incident_Trace_Log]]

## Source notes
- 數據每小時由 `ci_gate.py` 與 `compliance_to_wiki.py` 自動更新。
- **Commit SHA**: `d11aaff8d8cd10234dbfec74e2d5a6a012796cce`
- **Nexus Participation Ratio**: 85.0%

## Open questions / conflicts
- ⚠️ 目前某些邊緣測試案例的隔離性指標尚未完全自動化。

## 內容 (Content)
- **Timestamp**: 2026-04-08 11:09:40

### 🔍 Core Audit Dimensions (SOC2-like)
| Dimension | Status | Metrics |
|-----------|--------|---------|
| Isolation | ✅ PASS | leakage: 0.0 |
| Hallucination | ✅ PASS | rate: 0.0 |
| Concurrency | ✅ PASS | p95_latency: 4.033670822495565, recall: 0.98 |
| Security | ✅ PASS | audit_trail: PRESENT |
| Integration | ✅ PASS | latency: 2.3 |

### 🧱 Gate Summary
- **acceptance_check**: PASS
- **contract_check**: PASS
- **ci_gate_full_dry_run**: PASS

---
[[System Overview]]




[Source: scripts/ops/compliance_to_wiki.py]
