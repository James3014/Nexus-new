---
aliases:
- Pydantic Contracts
- Task Status Enum
- State Schemas
confidence: high
last_compiled: '2026-05-06'
owner: agent
related_pages:
- '[[04_State/State - Lifecycle.md]]'
- '[[06_Ops/Ops - Acceptance and Release.md]]'
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
本頁集中說明 Nexus 系統任務狀態契約與狀態轉移邏輯，並將其作為交付阻斷依據。

## Role / responsibility
- 定義 `Task` 相關的狀態欄位與轉移規範。
- 提供跨模組共用的可驗證狀態邊界。

## Upstream
- `nexus/orchestrator/task_contract.py`。
- `06_Ops/Ops - Closeout Hard Gate.md` 的完成條件。

## Downstream
- `04_State/State - Lifecycle.md`：生命週期文件對齊。
- `06_Ops/Ops - Acceptance and Release.md`：交付決策引用狀態結構。

## Related modules / files
- `nexus/orchestrator/task_contract.py`
- `nexus/orchestrator/task_state_transition.py`
- `tests/nexus/orchestrator/test_task_contract.py`

## Source notes
- 本頁內容沿用現行 task contract 架構與轉移限制整理。[Source: nexus/orchestrator/task_contract.py]

## Open questions / conflicts
- [ ] 是否將 `FAILED` 與 `REJECTED` 分離為不同恢復策略類型？
- [ ] 新增 `TEMP_FAILSAFE` 是否會影響 closeout 驗證流程？

## 🛡️ TaskStatus 實體枚舉 (Enums)
所有 `Task` 實體必須具備以下精確狀態：

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
- **Fail-Safe**: 偵測到非法轉移時，拋出 `ValueError`。

## Link to System
[[System Overview]]
