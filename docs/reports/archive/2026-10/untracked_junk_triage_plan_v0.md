# Untracked Junk Triage Plan v0 任務報告

## 1. 執行摘要 (Executive Summary)
本報告為 `untracked_junk_triage_plan_v0`，旨在對工作區內剩餘的未追蹤 (untracked) 非快取檔案進行精確分類，並提供後續的刪除、保留或 Commit 決策建議。
* **嚴格限制**：本任務為**純粹分類 (Triage-only)** 任務，**未執行任何檔案刪除**，亦未使用 `git clean`、`git reset` 或 `git restore` 等指令。
* **治理承諾**：所有暫存、原始碼與測試檔案皆完整保留，供 Owner 進行後續審查與決策。

## 2. 來源狀態 (Source State)
* **前置任務**：`safe_cache_and_log_cleanup_only_v0` 已經順利完成。本階段成功精確清理了 11,751 個檔案與 1,244 個目錄，主要阻斷了大量的 `.hypothesis` 與 Rust 編譯緩存噪音。
* **封存狀態**：Local 7B/14B Repair Expansion 的封存狀態維持 `PAUSED_ARCHIVED`，且 `next_execution_authorized` 依然為 `false`。

## 3. 當前未追蹤檔案清單 (Current Untracked Inventory)
在排除已清理的 cache/log/debug 之後，工作區內共有 **391** 個未追蹤項目：
* **分支 (Branch)**：`feature/bridge-fastmatcher-20260606`
* **頭部 Commit**：`7002b9f7`
* **主要頂層路徑**：
  * 重複/未審核證據類：`C_PHASE_*`、`NEXUS_FORENSIC_EVIDENCE_PACK.md`、`MagicMock/`
  * 評測輸出與驗證類：`benchmarking/swebench_lite/`、`verification-evidence/`
  * 專案代碼與測試類：`nexus/`、`tests/`、`subprojects/`、`test_localizer.py`、`test_prompt_builder.py`
  * 文件與報告類：`docs/adr/`、`docs/reports/`

## 4. 檔案歸類摘要 (Triage Categories)
經盤點，391 個未追蹤檔案被劃分為以下七大群組：
1. **`safe_delete_after_owner_approval`**：包含 Mock 工作區、臨時 reports 資料夾（如 `MagicMock/`、`tmp_storage/`、`parse_test*.py`）。
2. **`preserve_for_review_packet`**：包含 demo 輸出與 runtime 歷史證據（如 `artifacts/demo/`、`artifacts/original_baseline/`、`artifacts/runtime/` 內除本任務以外的歷史資料）。
3. **`formal_evidence_commit_candidate`**：包含正式階段性總結報告與 ADR（如 `C_PHASE_*`、`NEXUS_FORENSIC_*`、`docs/adr/0016-adr-search-to-ast-rewriter.md`）。
4. **`duplicate_or_imported_evidence_requires_review`**：先前的歷史證據包與 forensic 封包。
5. **`docs_candidate_requires_review`**：新增的 ADR 與歷史 Reports 文件。
6. **`benchmark_or_experiment_output_requires_review`**：SWE-bench predictions 與 verification 記錄。
7. **`source_or_test_candidate_do_not_delete`**：未追蹤但有實際修改的專案代碼與 unit/integration tests。

## 5. 安全刪除提案 (Safe-Delete Proposal)
以下為建議於 Owner 授權後安全刪除的低風險臨時檔案（目前尚未刪除）：
* **`MagicMock/`**：測試時動態生成的 Mock 工作區目錄。
* **`tmp_storage/`**：腳本執行時的臨時輸出。
* **`parse_test*.py`**：根目錄下的臨時解析除錯腳本。
* **`.tmp/untracked_files.txt`**：本 triage 步驟生成的臨時快照檔案。

## 6. 保留提案 (Preserve Proposal)
以下為必須保留不應刪除的檔案群組：
* **修復執行封存證據**：`artifacts/runtime/`
* **訓練與匯出邊界定義**：`configs/`
* **實驗與評測輸出**：`benchmarking/swebench_lite/` 與 `verification-evidence/`
* **專案代碼與測試**：`nexus/`、`tests/`、`subprojects/` 及其下屬檔案。

## 7. 正式證據 Commit 候選檔案 (Formal Evidence Commit Candidates)
建議將以下檔案作為本分支的歷史證據進行提交：
* **`C_PHASE_COMPLETION_REPORT.md`** / **`C_PHASE_STATUS.md`** / **`C_PHASE_VERIFICATION_EVIDENCE.md`**
* **`NEXUS_FORENSIC_EVIDENCE_PACK.md`**
* **`docs/adr/0016-adr-search-to-ast-rewriter.md`**

## 8. 刪除執行決策選項 (Deletion Execution Options)
未來 Owner 可對未追蹤 Junk 檔案做出以下決策：
* `APPROVE_SAFE_UNTRACKED_DELETE_ONLY` (僅刪除 safe-delete 提案中的臨時 mock 與 tmp 檔案)
* `APPROVE_FORMAL_EVIDENCE_COMMIT_REVIEW`
* `APPROVE_LOCAL_HEAL_HARDENING_REVIEW_PACKET`
* `APPROVE_S2T_EXPORT_ELIGIBILITY_REVIEW`
* `APPROVE_STRATA_S1_ALIGNMENT_REVIEW`
* `REMAIN_PAUSED_NO_DELETE`

## 9. 治理保全 (Governance Preservation)
* **封存鏈狀態**：`local_7b_14b_repair_expansion` 的封存狀態維持 `PAUSED_ARCHIVED`。
* **操作保證**：本任務絕無執行任何刪除、`git clean`、`git reset` 或 `git restore` 操作。無任何 source code 與 tests 被修改。
