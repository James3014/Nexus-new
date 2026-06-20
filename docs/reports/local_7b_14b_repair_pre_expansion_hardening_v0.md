# Local 7B/14B Repair Pre-Expansion Hardening v0 中文報告

本報告總結 `local_7b_14b_repair_pre_expansion_hardening_v0` 階段完成的工程硬化與治理工作。本次硬化全面補齊了煙霧批次（smoke batch）與下一擴展階段（expansion batch）之間的工程與安全落差。

---

## 成果摘要

本次任務共完成了 6 大硬化板塊 (Parts A-F)，全數單元測試 (18 個新測試案例) 均順利通過：

### Part A — MatchAuthority 恆定性與歸因分離
* **修改檔案**：`nexus/services/local_heal/errors.py`, `nexus/services/local_heal/patch_applier.py`
* **工程改動**：
  * 在 `MatchAuthority` Enum 中，新增了 `CANONICAL_RECOVERY` 憑證類型。
  * 修改 `PatchApplier.apply_and_validate()` 邏輯：凡是使用 `_lookup_canonical_search_span` 或 AST fallback 成功恢復之 SEARCH 區塊，均在套用時將歸因記錄為 `MatchAuthority.CANONICAL_RECOVERY`，與模型生成的 Verbatim 成功完全分離。
  * 確保 `FUZZY_CANDIDATE_ONLY` 永遠不可在 `success=True` 時回傳，從代碼層面落實 Invariant 驗證。
* **測試通過**：
  * `high_similarity_fuzzy_candidate_fail_closed`
  * `fuzzy_candidate_only_never_success`
  * `closest_match_diagnostic_only`
  * `canonical_recovery_not_model_success`
  * `cross_file_correction_requires_authority`

### Part B — MicroVerifier Venv 隔離與多層級狀態分類
* **修改檔案**：`nexus/services/local_heal/micro_verifier.py`
* **工程改動**：
  * 重構 `MicroVerifier.verify()`，使其接受 `verifier_env_metadata`，以取代寫死的系統 python3。
  * 對 import check 與 target test check，強制使用任務指定的 `interpreter` (例如專屬 venv Python)；若無指定且未授權 bare python3，則拒絕執行，返回 `ENV_BLOCKED` 狀態，有效防止環境 hang。
  * 分類體系全面支援：`syntax_parse_check`, `task_scoped_import_check`, `verifier_command_check`, `env_blocked`, `verifier_unavailable`, `false_pass_risk`, `false_fail_risk`。
* **測試通過**：已新增 `tests/unit/local_heal/test_micro_verifier.py` 並通過 5 個單元測試。

### Part C — StructuredPacket 重試引導鏈路對接
* **修改檔案**：`nexus/services/local_heal/corrector.py`, `nexus/services/local_heal/orchestrator.py`
* **工程改動**：
  * 在 `orchestrator.py` 遇測試失敗時，調用 `EvidenceCompactor.compact_structured()` 將 Traceback 編譯為 `StructuredPacket`。
  * 在 `corrector.py` 的 `build_retry_prompt` 中，若有 `StructuredPacket`，則將錯誤訊息結構化輸出，告知 LLM 出錯的 Exception Type、Location、Failing Source Span 和 Repro Command，並在 prompt 中安全地隱去全量 raw logs。
* **測試通過**：已新增 `tests/unit/local_heal/test_corrector_wiring.py` 並通過 4 個單元測試。

### Part D — Retry Metadata Schema 計數格式防呆
* **修改檔案**：`nexus/services/local_heal/receipt.py`
* **工程改動**：
  * 修正 `retry_count` 序列化公式為 `max(0, attempt - 1)`，徹底解決 initial failure 被多計 1 次的 count 漂移問題，確保 summary 與 receipts 計數完全一致。
* **測試通過**：已新增 `tests/unit/local_heal/test_retry_metadata.py` 並通過 4 個單元測試。

### Part E — Worktree Hygiene Plan 分類
* **產出**：已透過自動化腳本掃描 workspace，將 478 個 untracked 檔案精確分類為：`execution_evidence`, `runtime_code`, `tests`, `reports`, `build_cache`, `scratch_logs` 等，生成 `worktree_hygiene_plan.json`。結果為 `CLEAN_ENOUGH_FOR_APPROVAL_PACKET`。

### Part F — S2T / Training Export Guard 安全重新檢查
* **產出**：已確認當前 6 個 smoke 任務在硬化後依舊滿足安全邊界，`training_export_allowed = false`、`public_claim_allowed = false`、`automatic_adoption = false`。
