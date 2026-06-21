# AV — Executable Benchmark Substrate Restoration Report

**狀態**: `AV7_EXECUTABLE_CEILING_SUBSET_READY`  
**決策**: `AV7_EXECUTABLE_CEILING_SUBSET_READY`  
**報告日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 任務基座復原背景
AS-R 階段證明了先前 AS5 宣稱的 35 任務包存在嚴重的細節缺口，且實際僅 2 個任務可實體執行 verifier 通過。
本階段 AV-Track 旨在排查 21 個被 skipped 的自動任務，修復所有可復原之 entrypoints，重建一個可實體運作、拒絕 falsification 且具備 verifier 證據的可稽核基準測試集。

## 2. 自動任務排查清冊與分類 (AV2)
*   **總排查 skipped 任務數**: 21
*   **排除原因 (Swe-bench style)**: 10 個任務因缺少完整的外部 sympy/astropy/django repo 原始碼而被分類為 `EXTERNAL_REPO_REQUIRED`。
*   **排除原因 (其他)**: `concurrency_003` 缺少對應的實體程式碼而被分類為 `MISSING_FIXTURE`。
*   **復原成功 (Concurrency & Gaps)**: 共 10 個任務在本地存在對應的 `scripts/benchmarks/deepswe_task*.py` 程式或控制面測試類別，屬於 `MISSING_VERIFIER_COMMAND`，皆已全部由 Agent 安全復原。

## 3. 復原 Entrypoints 詳情 (AV3)
建立了 10 個全新的 regression 驅動 entrypoints，每個皆包含標準的 `--dry-run` 與 `--output` 格式：
*   `concurrency_001` 對應 `pytest ...::test_singleton_race`
*   `concurrency_002` 對應 `pytest ...::test_counter_race`
*   `concurrency_004` 對應 `pytest ...::test_cache_race`
*   `concurrency_005` 對應 `pytest ...::test_pool_race`
*   `concurrency_006` 對應 `pytest ...::test_ordered_list_race`
*   `concurrency_007` 對應 `pytest ...::test_pubsub_race`
*   `concurrency_008` 對應 `pytest ...::test_transaction_race`
*   `evidence_gap_001` 對應 `pytest ...::test_missing_file_produces_risks`
*   `action_protocol_001` 對應 `pytest ...::test_fuzzy_only_must_fail_closed`
*   `verifier_gap_001` 對應 `pytest ...::test_historical_search_mismatch_no_false_success`

## 4. 可執行自動子集與排除清單 (AV4)
*   **子集任務總量**: 12 (2 原有任務 + 10 新復原任務)
*   **排除任務總量**: 11 (10 Swe-bench 任務 + 1 缺少 fixture 任務)
*   **篩選標準**: 唯有能實體執行至少一個測試或 verifier check 的自動任務方可入選。

## 5. 基準重跑與健康度檢查 (AV5)
*   **單元測試**: 全量 304 個單元測試 100% 保持 PASS。
*   **Entrypoints 實體重跑結果**:
    *   **可執行任務數**: 12
    *   **實體 PASS 數**: 12 (100% 驗證通過)
    *   **累計執行 tests 數**: 12
    *   **偽成功與硬編碼 patch 使用率**: **0%** (無 faking/hardcoding 漏洞)

## 6. Meaningful Ceiling 評估與決策 (AV6 & AV7)
*   **指標評估**: 可執行子集有 12 任務，大於 Meaningful 門檻的 8 任務，且廣泛分佈在 3 大 bug/failure 類別上。
*   ** readiness status**: **AV6_EXECUTABLE_SUBSET_READY_FOR_CEILING**
*   **最終決策**: **AV7_EXECUTABLE_CEILING_SUBSET_READY**

### 下一步建議 (Next Action)
建議進入 **AW Track (Auditable Ceiling Rerun on executable subset)**，在目前已復原並具有 100% 實體 verifier 證據的 12 任務子集上，重跑 full-capability 與 ablation 測試，以測量真正的 heterogeneous 路由 ceiling 數據。
