# Post-Archive Worktree Hygiene and Next-Line Separation v0

## 1. Executive Summary
本報告正式記錄 Local 7B/14B 修復擴充能力沙盒封存後的「工作樹衛生與下一工作線分離」計畫。目前 Local 7B/14B repair expansion 已正式封存為 **PAUSED_ARCHIVED** 狀態，目前無任何新的執行任務被授權。

## 2. Archive Integrity
* **封存狀態 (Archive Status)**：`PAUSED_ARCHIVED`
* **來源終期彙整 (Source Rollup)**：`COMPLETE`
* **封存提交哈希 (Commit)**：`1c6f3b90`
* **決策授權**：`next_execution_authorized=false`，後續任何步驟皆須 Owner 新決策 (`owner_decision_required_for_any_next_step=true`)。
* **封存檔案完整性**：Claim boundary, residual risk, governance archive, next decision menu 皆存在，且校驗狀態為 **PASS**。

## 3. Dirty Worktree Inventory
目前 git 工作樹狀態如下：
* **目前分支 (Current Branch)**：`feature/bridge-fastmatcher-20260606`
* **HEAD 提交**：`1c6f3b90`
* **已追蹤但修改的檔案數 (Tracked Modified)**：37
* **未追蹤檔案數 (Untracked)**：120
* **暫存區檔案數 (Staged)**：0
* **工作樹狀態**：髒 (Dirty)

## 4. File Classification
目前工作樹中的 dirty 與 untracked 檔案被分類為以下八個主要區塊：
1. **已封印之已提交證據 (sealed_committed_evidence)**：已提交的 `local_7b_14b_repair_expansion_archive_v0` 檔案，不可篡改。
2. **未提交的正式證據 (formal_evidence_uncommitted)**：包含本工作樹衛生盤點檔案 (`post_archive_worktree_hygiene_v0/` 及本報告)。
3. **運行代碼候選 (runtime_code_candidate)**：包含未來工程線的 `local_heal` 修復代碼與 Rust 核心修改。
4. **測試代碼候選 (test_candidate)**：未提交的 `local_heal` 組件測試與 Django/Astropy 驗證器測試。
5. **文檔候選 (docs_candidate)**：文檔庫與 reports 目錄中未 commit 的 md 設計與 ADR 草稿。
6. **編譯緩存或生成檔 (build_cache_or_generated)**：包含 Rust `target/` 與 Python `__pycache__` 等編譯緩存。
7. **草稿與除錯日誌 (scratch_or_debug)**：包含本地執行日誌 `run_output*.log`、Ollama trace `ollama_calls.log` 及暫存 python 輔助腳本。
8. **基準與實驗輸出 (benchmark_or_experiment_output)**：包含 ad-hoc 實驗在 `benchmarking/` 目錄下生成的數據庫。

## 5. Do-Not-Commit List
以下類別將列入 **Do-Not-Commit** 清單，在未來清理前應保持忽略或排除，絕不可 commit 入穩定代碼分支中：
* Rust 編譯輸出 `nexus-core-rs/target/` (建議：`ignore`)
* Python 編譯字節碼 `**/__pycache__/` 及 `**/*.pyc` (建議：`ignore`)
* 本地除錯與草稿日誌 `*.log` (建議：`leave_untracked`)
* 暫存輔助腳本 `scratch/*.py` (建議：`leave_untracked`)
* Ad-hoc 實驗與基準測試記錄 `benchmarking/swebench_lite/*.jsonl` (建議：`leave_untracked`)

## 6. Candidate Commit Groups
未來可行的 commit 提交分組，本任務中**不進行任何暫存 (stage) 或提交 (commit)**：
* `archive_followup_evidence`：包括本盤點報告，建議在 owner 核准後 commit。
* `local_heal_transport_hardening_code`：包括 `local_heal` 連線與傳輸硬化核心代碼，建議未來切分出獨立工程分支 review。
* `local_heal_transport_hardening_tests`：包括對應單元測試，建議與代碼組共同 review。
* `s2t_export_guard_code_and_tests`：S2T 導出守衛代碼，屬於單獨的 S2T 審查線。
* `strategy_or_strata_candidate`：策略規劃與 StraTA 候選。
* `junk_cleanup_group`：編譯與草稿垃圾，在 owner 核准後進行安全清理。

## 7. Next-Line Options
Owner 後續可選的決策路徑如下：
1. `REMAIN_PAUSED_ARCHIVED` (保持封存)
2. `APPROVE_WORKTREE_CLEANUP_PLAN` (核准工作樹衛生清理計畫)
3. `APPROVE_LOCAL_HEAL_HARDENING_REVIEW_PACKET` (核准 `local_heal` 傳輸硬化新工程線審查)
4. `APPROVE_S2T_EXPORT_ELIGIBILITY_REVIEW` (核准 S2T 導出資格審查)
5. `APPROVE_STRATA_S1_ALIGNMENT_REVIEW` (核准 S1 對齊 readiness 審查)
6. `APPROVE_CONCURRENCY_REPEATABILITY_HARDENING` (核准併發重複性強化)
7. `APPROVE_NEXT_EXPANSION_APPROVAL_PACKET` (核准新一輪擴充包)

## 8. Recommendation
**強烈推薦決策：APPROVE_WORKTREE_CLEANUP_PLAN**。
由於當前工作樹極為髒亂，存在大量已追蹤但修改的檔案，以及未追蹤的編譯與草稿緩存。在開啟任何新的技術工程線或進行分支切分前，應優先執行非破壞性的工作樹衛生盤點與清理。

## 9. Governance Preservation
本盤點完全符合治理防禦防線：
* 新執行授權：`false`
* 訓練導出與 S2T 導出：`false`
* 公開與基準測試宣稱：`false`
* StraTA S1 與新擴充：`false`
* 後續行動一律要求 Owner 決策授權。
