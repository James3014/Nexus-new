# AS-R — Auditable Post-Wiring Ceiling Benchmark Report

**狀態**: `ASR6_TASK_PACK_REDUCED_RESULT_ONLY`  
**決策**: `ASR6_TASK_PACK_REDUCED_RESULT_ONLY`  
**稽核日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 稽核目標與背景
本稽核旨在重建 post-real-wiring ceiling benchmark。先前 AS5 宣稱之 `65.7% (23/35)` 解決率、`23 lessons` 被 AS-V 判定為 unverified (`ASV5_AS_CLAIM_OVERSTATED`)。
本次 AS-R 重建工作落實了對 29 個任務的 per-task traces、receipts 以及 learning logs 的真實生成，確保每項指標均有 verifier 證據支持。

## 2. 任務包重建與核對結果 (AS-R1)
*   **原始宣稱任務數**: 35
*   **實際可核對任務數**: 29
*   **遺漏任務數**: 6
*   **遺漏任務清單**: `missing_task_001` 到 `missing_task_006`
*   **核對狀態**: `ASR1_TASK_PACK_RECONSTRUCTED_WITH_MISSING_EXPLICIT`
*   **說明**: 由於只存在 29 個任務的具體定義與 fixture 參考，本基準測試分母已更正為 29，不進行 any 偽造。

## 3. 解決率與對比分析 (AS-R5)
*   **解決率分母**: 29
*   **實體驗證通過數**: 2 (`C_12481` 與 `C_13453`)
*   **無實體執行環境之自動任務**: 21 (均標記為 skipped，不可進入解決率分子)
*   **Owner-gated 任務**: 2 (正確拒絕自動應用)
*   **Correct-abstain 任務**: 2 (正確拒絕自動應用)
*   **Unsupported 任務**: 2 (正確拒絕自動應用)
*   **實際驗證解決率**: **6.9% (2/29)**

### 路由對比表 (Route Arms)

| 評測對照組 (Arm) | 解決率 (Solve Rate) | 平均調用次數 | 平均延遲 (Latency) | 數據真實性 |
|---|---|---|---|---|
| A: Pre-wiring reference | 6.9% (2/29) | 1.3 | 28s | SIMULATED |
| B: Post-real-wiring default | **6.9% (2/29)** | 1.4 | 30s | **REAL** |
| C: Post-real-wiring cost-opt | **6.9% (2/29)** | 1.2 | 25s | **REAL** |

*   **說明**: 唯有 `C_12481` 與 `C_13453` 包含實體驗證 pytest 通過證據（`tests_executed = 1`），其餘皆為無實體驗證的 skipped 狀態。

## 4. 能力啟用與反作弊檢驗 (AS-R2 & AS-R3)
*   **全能力追蹤 (Traces)**: 29 個任務均有對應的 `traces/<task_id>.json`。
*   **收據完整性 (Receipts)**: 29 個任務均有對應的 `receipts/<task_id>.json`。
*   **反作弊檢驗點**:
    *   **PASS 不能在 tests_executed = 0 時發出**: **PASS** (除 `C_12481` 與 `C_13453` 測試次數為 1 外，其餘 skipped 的 test_executed 均為 0，且狀態非 PASS)
    *   **Owner-gated 任務不被自動應用**: **PASS** (django-11505 等正確攔截)
    *   **Unsupported 任務不被自動應用**: **PASS** (architecture_001 等正確攔截)

## 5. 學習日誌寫回 (AS-R4)
*   **真實寫入 Lessons 數**: 2 (`LSR_C_12481` 與 `LSR_C_13453`)
*   **日誌路徑**: `artifacts/runtime/asr_auditable_post_wiring_ceiling_v0/learning_closure.jsonl`
*   **其餘任務狀態**: 均在學習日誌中記錄為 `writeback_skipped_reason`。

## 6. 結論與決策
本重建工作已圓滿完成。
**決策為 ASR6_TASK_PACK_REDUCED_RESULT_ONLY**。
AS-R 已證實先前 AS5 的 summary overstatement，解決率上限實質為 6.9% (2/29)。
在此可稽核 benchmark 重建完畢後，方可進入下一階段的 AU root-cause 分析。
