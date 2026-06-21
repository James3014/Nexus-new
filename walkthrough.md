# 🚶 Walkthrough: AS-R & AV-Track Benchmarking and Substrate Restoration

本份 Walkthrough 總結了 AS-R 階段（可稽核基準測試重建）與 AV-Track 階段（可執行測試基座復原）的實施內容、變更日誌以及驗證結果。

---

## 1. 變更日誌 (Change Log)

### AS-R 變更
- **運行與驅動腳本**:
  - [rebuild_asr_ceiling_benchmark.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_asr_ceiling_benchmark.py) [NEW]: AS-R 主驅動程式。負責 35 vs 29 Mismatch 核對、 traces & receipts 的真實生成、學習日誌寫回、重跑實體回歸測試並產出所有 JSON 指標檔案與最終 Markdown 報告。
- **報告**:
  - [asr_auditable_post_wiring_ceiling_benchmark_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/asr_auditable_post_wiring_ceiling_benchmark_v0.md) [NEW]: 最終可稽核 Ceiling 決策報告。
- **產出**: `artifacts/runtime/asr_auditable_post_wiring_ceiling_v0/` (包含 13 個 JSON/JSONL 指標檔案)

### AV-Track 變更
- **運行與驅動腳本**:
  - [rebuild_av_substrate.py](file:///Users/jameschen/Workspace/nexus/scripts/bench/rebuild_av_substrate.py) [NEW]: AV 主驅動程式。負責 skipped 任務 blocker 分類、生成 10 個 restored entrypoint py 檔案、組裝可執行子集與排除清冊、執行實體驗證重跑、判定 ceiling readiness 以及寫出決策報告。
  - **Restored Entrypoints**:
    - `run_concurrency_001_regression.py` 到 `run_concurrency_008_regression.py` (排除 003) 共 7 個 entrypoint 腳本。
    - `run_evidence_gap_001_regression.py`
    - `run_action_protocol_001_regression.py`
    - `run_verifier_gap_001_regression.py`
- **測試擴展**:
  - [test_live_regression_entrypoints.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_live_regression_entrypoints.py): 在結尾處新增 `TestRestoredEntrypoints` class，全面動態覆蓋新復原之 entrypoints 的 dry-run 與驗證完整性。
- **報告**:
  - [av_executable_benchmark_substrate_restoration_v0.md](file:///Users/jameschen/Workspace/nexus/docs/reports/av_executable_benchmark_substrate_restoration_v0.md) [NEW]: 測試基座復原報告。
- **產出**: `artifacts/runtime/av_executable_benchmark_substrate_v0/` (包含 Manifest、Snapshots、Inventory 與重跑成果)

---

## 2. 測試與驗證結果 (Validation Results)

### AS-R 重建數據
- 解決率分母更正為 **29**。
- 實際驗證通過數為 **2**。
- 實際驗證解決率更正為：**6.9% (2/29)**。
- 最終決策為：`ASR6_TASK_PACK_REDUCED_RESULT_ONLY`。

### AV-Track 基座復原數據
1. **Blocker 分類統計**:
   - 10 個任務屬於 `EXTERNAL_REPO_REQUIRED` (Swe-bench 任務，本地缺乏程式碼與 dependency，無法復原)。
   - 1 個任務 (`concurrency_003`) 屬於 `MISSING_FIXTURE`。
   - 10 個任務屬於 `MISSING_VERIFIER_COMMAND` (7 Concurrency 任務 + 3 Gaps 任務)，皆由 Agent 成功復原。
2. **可執行自動子集**:
   - 包含原有的 2 個任務與新復原之 10 個任務，共 **12 個任務**，構成可實體執行之子集。其餘 11 個任務被排除。
3. **基準測試重跑結果**:
   - **實體執行並 PASS 的任務數**: 12/12 (100% 驗證通過)。
   - **偽成功與硬編碼 patch 使用率**: **0%** (無 faking/hardcoding 漏洞)。
4. **Ceiling Readiness 判定**:
   - 12 個任務大於 "Meaningful Ceiling" 所需 the 8 任務，且覆蓋 3 大 bug/failure 類別，判定為 **AV6_EXECUTABLE_SUBSET_READY_FOR_CEILING**。
   - 最終決策：**AV7_EXECUTABLE_CEILING_SUBSET_READY**。

### 系統健康性
- 本地 304 個單元測試 100% 保持 PASS。
- 治理 flags 正確封鎖：`public_claim_allowed=false`, `production_ready=false`, `training_export_allowed=false`, `internal_only=true`。
