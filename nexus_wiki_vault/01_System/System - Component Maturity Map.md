---
aliases: '[System Maturity Map, Component Health]'
confidence: high
last_compiled: '2026-05-06'
owner: agent
source_of_truth: compiled-wiki
status: active
tags: '[system, maturity, risk]'
title: System Component Maturity Map
type: system
version_scope: '[v26]'
---

# 🩺 System Component Maturity & Health Map

## 📊 成熟度階梯 (Maturity Ladder)
本頁引導 Agent 在對位不同組件時，應採取何種強度的風險控制。

| Component | Maturity | Status | Guardrails |
|---|---|---|---|
| **Nexus Engine** | 🌲 **STABLE** | Production | 100% CI pass required. |
| **Governance CLI**| 🌲 **STABLE** | Production | Enforced preflight mandatory. |
| **Master Loop** | 🌲 **STABLE** | Production | L4/L3 boundaries enforced. |
| **Drone Engine** | 🌲 **STABLE** | Production | 1-bit Core & GBNF hardened. |
| **MSA Routing** | 🌿 **EVOLVING** | Beta | LanceDB Real Retrieval enabled. |
| **Bonsai Brain** | 🌿 **EVOLVING** | Beta | Health checks & JSON self-healing. |

## 🛡️ 操作指引 (Operational Guidelines)

### 1. 🌲 STABLE (穩定區)
- **要求**: 修改必須具備 ADR 支撐，且通過「全域回歸測試」。
- **Agent 行為**: 嚴禁任何破壞性修改，優先保持舊版相容性 (Shim layers)。

### 2. 🌿 EVOLVING (演進區)
- **要求**: 需附帶詳細的測試報告與效能對標數據。
- **Agent 行為**: 允許架構微調，但必須保留明確的物理回滾路徑。

### 3. 🧪 EXPERIMENTAL (實驗區)
- **要求**: 必須在獨立目錄 (Sandbox) 運行，嚴禁干擾主線。
- **Agent 行為**: 快速迭代，優先驗證可行性而非系統整合度。

---
**[Source: nexus_wiki_vault/01_System/System - Component Maturity Map.md]**

## One-sentence summary
組件成熟度地圖定義各模組在穩定度、風險與治理要求上的分層狀態，幫助決策不同變更策略。

## Role / responsibility
- 指引不同成熟度組件的修改準則與安全閘門。

## Upstream
- [[01_System/System Relationship and Dependency Graph|System Relationship and Dependency Graph]]
- [[01_System/Code_Ownership_Matrix|Code Ownership Matrix]]

## Downstream
- [[05_Governance|Governance]]
- [[06_Ops/Ops - Closeout Hard Gate|Closeout Hard Gate]]

## Related modules / files
- [Source: compiled-wiki]
- [[System Overview]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- 是否需要將「EVOLVING/EXPERIMENTAL」轉換到可量化閘門數值，便於自動化決策？
