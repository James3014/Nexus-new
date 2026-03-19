# Nexus Dynamic Feedback Loop Injection (TDD Plan)

## Objective
我們需要讓 Nexus 的 `R -> A` (Repair -> Audit) 重試迴圈具備「痛覺傳遞」功能。當 Agent 的修改被拒絕時，必須把具體的拒絕理由回傳給 Agent，而不是讓它無腦重試。

## TDD TODOs

### 1. Test Generation (`tests/test_dynamic_feedback.py`)
- [ ] 建立一個單元測試，模擬 `RepairPhaseHandler` 被呼叫時。
- [ ] 測試當 `state.metadata.get("last_audit_failure")` 存在時，它會被正確抽取並作為 Context 注入給底層的 CodexLoop 提示詞或傳遞給 Agent 的 Prompt。
- [ ] 測試 `pipeline.py` 在 `Audit PASS blocked` 時，會把明確的錯誤字串存入 `state.metadata["last_audit_failure"]`。

### 2. Implementation (`nexus/engine/pipeline.py`)
- [ ] 在 `pipeline.py` 檢查 `audit_success` 失敗時（如 `missing no_change_reason`），將報錯訊息存入 `state.metadata["last_audit_failure"]`。
- [ ] 在迴圈重試 `continue` 之前，確保 `pack["audit_feedback"]` 也一併更新，便於直接傳遞給下一輪的 `repairer.run(state, pack)`。

### 3. Implementation (`nexus/engine/phases/repair.py`)
- [ ] 修改 `RepairPhaseHandler.run`。在組裝給 Agent / CodexLoop 的任務描述時，如果 `pack` 裡面包含 `audit_feedback` 或者 `state.metadata` 有 `last_audit_failure`，強烈地將其置於任務最前方：
      `⚠️ [System Audit Warning]: Your previous attempt was REJECTED because: {feedback}`

## Execution
請使用本指南進行 TDD 開發。這將由 `git-manager` 分身工作區驅動。
