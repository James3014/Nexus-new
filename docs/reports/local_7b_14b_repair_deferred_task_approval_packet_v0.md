# Local 7B/14B Repair Deferred Task Approval Packet v0

## 1. Executive Summary
本報告準備關於延期任務（deferred tasks）的 Owner 決策封包。本封包旨在協助 Owner 評估與決策是否啟動後續延期任務，**不代表直接授權或執行該任務**。當前封包狀態為 **READY_FOR_OWNER_DECISION**。

## 2. Source Closure
先前的 4-task controlled expansion batch 已完成並封閉，其最終狀態為 **CLOSED_WITH_WARNING** (commit: `de475b0f`)。3/3 模型生成的修復嘗試均成功通過驗證，1/4 為 workspace_pre_verified（不計入 model repair success）。

## 3. Deferred Tasks
本封包內含 2 個延期任務：
- `concurrency_bug_03`: 併發與等冪性重複測試任務，旨在驗證模型於 Race Condition / Deadlock 風險下的修復重複性。
- `sympy_matrices_abstention_candidate`: 棄權候選任務，旨在驗證模型在證據不足時是否能正確執行棄權，而非強行生成錯誤修復。

## 4. Risk Comparison
- `concurrency_bug_03`: 具備高併發下的不確定性與 flakiness 風險。需要嚴密的測試線路以確保其 repeatable。
- `sympy_matrices_abstention_candidate`: 具備模型修復成功率解讀風險，考驗模型是否能遵守邊界限制進行正確棄權。
- **總結**: 兩者均為 local 級別修復能力之驗證，均不具備訓練數據導出合規性，亦無 runtime 整合授權。

## 5. Recommended Option
- **推薦選項**: `APPROVE_CONCURRENCY_ONLY_EXECUTION` (僅授權 concurrency_bug_03 執行)
- **理由**: `concurrency_bug_03` 為先前 batch 殘留之已知執行風險任務，應單獨隔離執行以獲取乾淨的 repeatability 訊號。棄權測試不宜與併發測試混合於同一輪，以利結果分析。

## 6. Guardrails
延期任務在執行時必須遵守以下嚴格安全護欄：
- 每次僅能執行一個延期任務。
- 必須使用 task-scoped 虛擬環境 (venv)，不允許 bare python3。
- MicroVerifier 僅為前置語法檢查器，完整驗證器 (Full Verifier/pytest) 依然為最終判定 Authority。
- 嚴禁任何 timing hack 或任意的 sleep-based 通過。
- 嚴禁弱化測試 (no test weakening)。
- 棄權任務允許以正確棄權 (abstained) 作為正確輸出。
- 無公開宣稱，無訓練數據導出，無自動採納。

## 7. Governance
確認本封包建立期間：
- `model_calls_executed`: false
- `repair_execution_authorized`: false
- `runtime_integration`: false
- `routing_integration`: false
- `verifier_override`: false
- `training_export_allowed`: false
- `public_claim_allowed`: false
- `automatic_adoption`: false
- `s2t_export_allowed`: false
- `owner_decision_required`: true

## 8. Owner Decision Options
Owner 可以從下列選項中做出後續決策：
- `APPROVE_CONCURRENCY_ONLY_EXECUTION` (推薦)
- `APPROVE_ABSTENTION_ONLY_EXECUTION`
- `APPROVE_DEFERRED_TASK_EXECUTION_BOTH`
- `REQUEST_MORE_HARDENING`
- `PAUSE_AND_ARCHIVE_EXPANSION_BATCH`
