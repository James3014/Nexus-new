---
title: Incident Trace Log
type: compliance
status: active
version_scope: v22.5
owner: agent
confidence: high
last_compiled: 2026-04-17
source_of_truth: 06_Ops/Ops - CI Failure Playbook.md
tags:
  - incident
  - traceability
  - compliance
---

# 🛡️ SLA Incident Logs (v22.5 - Traceability)
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

## One-sentence summary
本表保留失敗事件軌跡與信任層級，用於回溯重工與隔離重複失敗樣式。 [Source: 06_Ops/Ops - CI Failure Playbook.md]

## Role / responsibility
- 記錄高風險任務失敗事件，支持事件回顧與回歸修正。 [Source: 06_Ops/Ops - CI Failure Playbook.md]
- 導出 Scope Drift 具體樣本給 Root Cause 分析流程。 [Source: nexus/core/orchestrator.py]

## Upstream
- **[06_Ops/Ops - CI Failure Playbook](../06_Ops/Ops - CI Failure Playbook.md)**: 提供事件處置指引。 [Source: 06_Ops/Ops - CI Failure Playbook.md]
- **[06_Ops/Ops - Governance Changelog](../06_Ops/Ops - Governance Changelog.md)**: 將重大異常納入治理週期。 [Source: 06_Ops/Ops - Governance Changelog.md]

## Downstream
- **[07_Compliance/Current_Compliance_Status](Current_Compliance_Status.md)**: 同步事件失敗率與整體狀態。 [Source: 07_Compliance/Current_Compliance_Status.md]
- **[06_Ops/Ops - SLO Dashboard](../06_Ops/Ops - Governance SLO Dashboard.md)**: 將事件結果納入監控趨勢。 [Source: 06_Ops/Ops - Governance SLO Dashboard.md]

## Related modules / files
- `06_Ops/Ops - CI Failure Playbook.md`
- `scripts/ops/ci_gate.py`
- `06_Ops/Ops - Governance Changelog.md`

## Source notes
- 失效樣本主要集中於 scope_drift（跨任務邊界偏差）。 [Source: 06_Ops/Ops - CI Failure Playbook.md]

## Open questions / conflicts
- [ ] 是否需要增加 Scope Drift 的前置預警特徵標籤？
- [ ] 事件信任度分級是否要加入 evidence_bundle 完整度維度？

**[Source: 06_Ops/Ops - CI Failure Playbook.md]**

[[System Overview]]
