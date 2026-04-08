---
title: "Incident Trace Log"
aliases: "SLA Incident Logs"
confidence: high
last_compiled: "2026-04-08"
owner: agent
source_of_truth: "scripts/ops/compliance_to_wiki.py"
status: active
tags: "[compliance, incident, sla]"
type: log
version_scope: "[v22.5]"
---

# 🛡️ SLA Incident Logs (v22.5 - Traceability)

## One-sentence summary
本頁面追蹤 Nexus 系統中 SLA 失效的具體事件及其根本原因分析。

## Role / responsibility
- **回溯**: 提供失敗任務的 Traceability，協助開發者定位 scope drift 或邏輯漏洞。
- **治理**: 作為信任等級（Trust Level）評定的依據。

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 總體治理入口。
- `scripts/ops/compliance_to_wiki.py`

## Downstream
- [[07_Compliance/Current_Compliance_Status]]
- [[07_Compliance/Compliance_Dashboard]]

## Related modules / files
- [[06_Ops/Ops - CI Failure Playbook]]
- [[06_Ops/Ops - Learning Closure Matrix]]

## Source notes
- 記錄所有 exit code 非零或觸發治理守門失敗的任務。

## Open questions / conflicts
- ⚠️ 部分 `unknown` 根本原因需要人工接入複審。

## 內容 (Content)
| Timestamp | Task ID | Result | Root Cause | Trust Level |
|-----------|---------|--------|------------|-------------|
| 2026-03-23T20:32:40.293585 | feat-1774269160 | ❌ FAIL | unknown | untrusted |
| 2026-03-23T20:32:41.556372 | feat-1774269160 | ❌ FAIL | unknown | untrusted |
| 2026-03-30T18:36:46.797123 | OFF-001 | ❌ FAIL | scope_drift | untrusted |
| 2026-03-30T21:37:22.242919 | bug-1774877789 | ❌ FAIL | scope_drift | untrusted |
| 2026-03-30T21:38:44.280606 | feat-1774877887 | ❌ FAIL | scope_drift | untrusted |
| 2026-03-30T21:50:51.289329 | bug-1774878600 | ❌ FAIL | scope_drift | untrusted |
| 2026-03-30T21:52:20.653464 | feat-1774878699 | ❌ FAIL | scope_drift | untrusted |
| 2026-03-31T07:56:33.321018 | bug-1774914937 | ❌ FAIL | scope_drift | untrusted |
| 2026-03-31T07:57:54.986824 | feat-1774915033 | ❌ FAIL | scope_drift | untrusted |
| 2026-03-31T08:03:21.450223 | bug-1774915350 | ❌ FAIL | scope_drift | untrusted |

---
[[System Overview]]




[Source: scripts/ops/compliance_to_wiki.py]
