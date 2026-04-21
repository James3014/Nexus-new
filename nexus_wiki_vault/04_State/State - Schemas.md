---
aliases:
- Pydantic Contracts
- Task Status Enum
- State Schemas
confidence: high
last_compiled: 2026-04-21
owner: agent
related_pages:
- '[[16_STATE_LIFECYCLE_AND_METABOLISM_PRUNING]]'
source_of_truth: nexus/orchestrator/task_contract.py
status: hardened
tags:
- state
- pydantic
- status
- transition
title: State - Schemas
type: state
version_scope:
- v24.1
- v26
---

# State - Schemas (v26 Pydantic Enforced)

## One-sentence summary
本頁集中說明 Nexus 系統內所有 `Task` 相關的 Pydantic 契約數據結構與嚴格的狀態轉移 (State Transition) 規約。

## 🛡️ TaskStatus 實體枚舉 (Enums)
所有的 `Task` 實體必須具備以下精確狀態：

| Status | Category | Description |
| :--- | :--- | :--- |
| `CREATED` | Start | 任務初始化。 |
| `ASSIGNED`| Active | 任務已委派至 Drone。 |
| `IN_PROGRESS`| Active| 執碼中 (P-X 階段)。 |
| `READY_FOR_REVIEW`| Verify| 進入 D-R-A 審計鏈。 |
| `INTEGRATED`| Done | 補丁已 Promote。 |
| `CLOSED` | Done | 任務完全結案。 |
| `REJECTED` | Failure| 幻覺指数超標，回退至修復。 |
| `FAILED` | Failure| 無法修復。 |

## ⚙️ 狀態轉移驗證 (Transition Rules)
系統透過 `TaskStateTransition.validate_transition` 強制執行物理阻斷：
- **合法**: `CREATED -> ASSIGNED -> IN_PROGRESS`。
- **非法**: 禁止 `CREATED -> INTEGRATED` (繞過審計)。
- **Fail-Safe**: 偵測到非法轉移時，物理拋出 `ValueError`。

---
Back to [[System Overview]]
