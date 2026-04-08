---
title: "Compliance Dashboard"
aliases: "Nexus Compliance Dashboard"
confidence: high
last_compiled: "2026-04-08"
owner: agent
source_of_truth: "scripts/ops/compliance_to_wiki.py"
status: active
tags: "[compliance, dashboard, governance]"
type: dashboard
version_scope: "[v22.5]"
---

# 📊 Nexus Compliance Dashboard (FedRAMP/SOC2 Readiness)

## One-sentence summary
本面板彙整了 Nexus 的 SLA 指標、合規控制點及治理審核狀態，提供即時的視覺化監控。

## Role / responsibility
- **決策**: 供營運團隊快速評估當前系統穩定性（🟡 WATCH / ✅ GREEN）。
- **驗證**: 整合所有合規證據的入口。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 總體治理入口。
- [[07_Compliance/Current_Compliance_Status]]
- [[07_Compliance/Incident_Trace_Log]]

## Downstream
- [[06_Ops/Ops - Governance SLO Dashboard]]

## Related modules / files
- [[06_Ops/Ops - Ownership and Review SLA]]
- [[99_Norms/治理規範]]

## Source notes
- 數據彙整自多個治理腳本。

## Open questions / conflicts
- ⚠️ SLA 成功率目前仍低於目標值 (32.19% < 95%)。

## 內容 (Content)
### 🎯 SLA 實時指標 (SLA Real-time Metrics)
- **當前任務總數**: 4023
- **SLA 成功率**: 32.19% (目標: >95%)
- **穩定性等級**: 🟡 WATCH

### 🎯 Live Controls
- **[Readiness Assessment (A1)](../07_Compliance/Current_Compliance_Status.md)**
- **[FedRAMP Traceability (B2)](../07_Compliance/Incident_Trace_Log.md)**
- **[SLA Evidence (C1/C2)](../06_Ops/Ops - Ownership and Review SLA.md)**

### 🛡️ Monthly Governance Review Status
| Check | Owner | Last Run | Status |
|-------|-------|----------|--------|
| Permissions Audit | Owner A | Today | ✅ PASS |
| Vulnerability Scan | Owner B | Yesterday | ✅ PASS |
| SLA Monthly Report | Owner C | N/A | ⏳ PENDING |

[Source: scripts/ops/compliance_to_wiki.py]

---
[[System Overview]]


[Source: scripts/ops/compliance_to_wiki.py]
