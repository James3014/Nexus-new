---
aliases: '[Ownership, Domain Control, Responsibilities]'
confidence: high
last_audit: '2026-04-21 16:45'
last_compiled: '2026-04-21'
owner: agent
source_of_truth: git-shortlog-refactor-v32.6
status: sealed
tags: '[system, ownership, rbac, matrix]'
title: System - Code Ownership Matrix
---

# System - Code Ownership Matrix (v26 Hardened)

## 👥 領域擁有權矩陣 (Ownership Matrix)

| Module Path (路徑) | Primary Owner | Backup Agent | Accountability (責任) |
| :--- | :--- | :--- | :--- |
| `nexus/engine/` | **Antigravity** | Gemini-Nexus | 執行管線、狀態機誠信與 CLI 核心。 |
| `nexus/governance/` | **Antigravity** | Codex | 門禁審計、HI 計分、CapabilityGate 與規約。 |
| `nexus/events/` | **Codex** | Antigravity | 信號輸入 (Ingress)、日誌存儲 (Store) 與傳輸。 |
| `nexus/services/` | **Gemini-Nexus**| Antigravity | 基礎設施、向量檢索與 API 支援。 |
| `nexus/core/` | **Shared (Facades)**| - | 僅限兼容外觀 (Facades) 與共用常量。 |

## 🛡️ 審計與修改主權
- **Governance (治理層)**: 修改必須由 Antigravity 物理簽署。
- **Events (事件層)**: 負責高併發一致性，由 Codex 監控資料流。
- **Engine (引擎層)**: 負責 P-X-D-R-A-C 動力，由 Antigravity 管控。

---
**[Source: compiled-wiki]**

## One-sentence summary
本頁定義模組維護主責與備援代理邊界，規範跨模組修改時的權限與責任。

## Role / responsibility
- 作為跨模組協作的主權準則，防止未授權修改與責任不清。

## Upstream
- [[01_System/Supreme_Master_Loop_Spec|Supreme Master Loop Spec]]
- [[01_System/Identity_Vault|Identity Vault]]

## Downstream
- [[06_Ops/Ops - Governance Changelog|Governance Changelog]]
- [[07_Compliance/Current_Compliance_Status|Current Compliance Status]]

## Related modules / files
- [Source: compiled-wiki]
- [Source: 01_System/System Relationship and Dependency Graph.md]
- [[System Overview]]

## Source notes
- [Source: compiled-wiki]

## Open questions / conflicts
- 是否應為 `nexus/core` 的 shared facades 增加清晰的撤銷程序與審批期限？
