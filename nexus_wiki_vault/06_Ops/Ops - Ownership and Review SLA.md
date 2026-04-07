---
last_compiled: 2026-04-06
owner: agent
status: active
tags:
- governance
- ownership
- sla
- compliance
title: Ops - Ownership and Review SLA
type: ops
---



# Ops - Ownership and Review SLA

## One-sentence summary
本頁面定義 Nexus Wiki 條目的所有權歸屬、編校頻率與服務等級協議 (SLA) 標準。 [Source: scripts/ops/wiki_owner_audit.py]

## Role / responsibility
- **權威歸屬定義**: 確保每個核心模組頁面均有明確的人工或 Agent 負責人。
- **時效性監核**: 定義 30 天編校週期，防止系統知識陳舊化 (Stale Knowledge)。
- **SLA 追蹤**: 生成合規性報表，作為治理健康度的核心指標。

## SLA Matrix (服務等級協議表格)
| Level | Page Type | Review Period | Action on Expiration |
|---|---|---|---|
| **Critical** | [Home](../00_Home/System Overview.md), Ops, Prot | 30 Days | High Priority Warning |
| **Standard** | Modules | 45 Days | Standard Notification |
| **Backup** | Source | 90 Days | Passive Monitor |

## Upstream
- **[System Overview](../00_Home/System Overview.md)**: 總覽。
- **[Ops - Governance SLO Dashboard](Ops - Governance SLO Dashboard.md)**: 指標看板。

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: 禁止帶有 Stale 核心頁面的版本發佈 (未來)。

## Related modules / files
- `/scripts/ops/wiki_owner_audit.py`: 產權稽核腳本。

## Source notes
- v22 Engine Spec Part 3:「凡物理邏輯必有主，凡文檔聲明必有核」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Agent Transition**: 當 Agent 版本升級時，如何自動移交 Ownership 權限。

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]