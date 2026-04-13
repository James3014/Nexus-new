# Nexus 分層測試方案 (Layered Testing Plan)

## 1. 執行層級與觸發時機

| 層級 | 名稱 | 觸發時機 | 預期耗時 |
| :--- | :--- | :--- | :--- |
| **L1** | 快速驗證層 | 每次 Git Commit (Pre-commit) | < 30s |
| **L2** | 變更關聯層 | PR 提交前、開發階段完成 | 1-3 min |
| **L3** | 全量回歸層 | 合併至 Master 前、夜間自動化 | > 5 min |

## 2. 外部依賴警告聲明
- **LanceDB Deprecation**: 來自 `site-packages/lancedb` 的警告（如 `table_names()`）屬於外部依賴演進，**不視為內部代碼回歸失敗**。
- **Requests Dependency**: 已透過專案 `.venv` 內的 pytest 密封對齊解決。

## 3. 執行指令
詳見 [Test Runbook](./test_runbook.md)。
