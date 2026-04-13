# AutoResearch 執行與守門手冊 (v1.0)

## 1. 啟動流程
1. **定義範圍**: 在任務描述或配置中明確 `modifiable_scope` (建議僅限研究用模組)。
2. **配置評估**: 確保 `UnifiedEvaluator` 已配置固定 Seeds 與 Budget。
3. **執行研究**: 使用群集指令啟動 Phase R (Research)。

## 2. 物理守門規則

| 情境 | 行動 | 理由 |
| :--- | :--- | :--- |
| **指標提升 > 10%** | **PROMOTE** | 通過多 Seeds 驗證且具備統計意義。 |
| **指標退化或門檻未過** | **SAFE ROLLBACK** | 觸發 `SelectorRollback.restore_scope` 回復至實驗前狀態。 |
| **非法檔案寫入** | **ABORT** | `ExperimentScheduler` 將主動阻斷超出 Scope 的寫入嘗試。 |
| **資源耗盡** | **HUMAN TAKEOVER** | 超出 Budget 時暫停，由工程師評估是否繼續。 |

## 3. 失敗排查與清理
- **磁碟空間**: 若出現 `Errno 28`，請執行 `rm -rf .nexus/experiments/*`。
- **回滾手動檢查**: 若自動回滾失敗，可檢查 `.nexus/backups/[CandidateID]` 進行手動恢復。
- **併發控制**: 禁止在同一工作區並發執行多個研究實驗。
