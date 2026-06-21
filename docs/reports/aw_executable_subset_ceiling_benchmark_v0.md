# AW-Track 可執行子集 Ceiling 基準測試 Rerun 報告 (AW6 最終決策)

## 1. 執行摘要 (Executive Summary)

本報告針對經由 AV-Track 復原並實體驗證通過的 12 個「可執行自動任務子集」 (Executable Automatic Subset) 進行 AW-Track Ceiling 基準測試 rerun。
本項測試為**內部專用 (Internal-only) 可執行子集 Ceiling 測量**，並不代表原始的 35 任務 Ceiling，亦不涉及產品化 (Productization)、公開宣稱 (Public claim)、14B 模型探索或強模型 bare 對照。

* **AW6 最終決策**: `AW6_EXECUTABLE_SUBSET_CEILING_CONFIRMED`
* **可執行子集解決率**: **12/12 PASS (100.0%)**
* **聲明邊界**: "Current executable automatic subset is fully covered. (當前可執行自動子集已完全覆蓋)。" **嚴禁宣稱 Nexus 全量 Ceiling 為 100%**。
* **治理參數**:
  * `public_claim_allowed` = `false`
  * `production_ready` = `false`
  * `training_export_allowed` = `false`
  * `internal_only` = `true`

---

## 2. 凍結可執行子集清冊 (AW1)

可執行子集共包含 12 個任務，已於 [frozen_subset_manifest.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/aw_executable_subset_ceiling_v0/frozen_subset_manifest.json) 中鎖定。

| 任務 ID | 任務來源 | 失敗類別 | Expected Boundary | Why Included / 納入原因 |
| :--- | :--- | :--- | :--- | :--- |
| `C_12481` | C-Track Regression | Uncertainty Route / Real Wiring | AUTOMATIC | 驗證 real repair 任務之異質路由 Selector 真實接線狀態。 |
| `C_13453` | C-Track Regression | Uncertainty Route / Real Wiring | AUTOMATIC | 驗證 real repair 任務之異質路由 Selector 真實接線狀態。 |
| `concurrency_001` | Concurrency Suite | Race Condition / Singleton | AUTOMATIC | 檢驗 Singleton 併發 Race 檢測與防禦機制。 |
| `concurrency_002` | Concurrency Suite | Race Condition / Counter | AUTOMATIC | 檢驗 Counter 併發 Race 檢測與防禦機制。 |
| `concurrency_004` | Concurrency Suite | Race Condition / Cache | AUTOMATIC | 檢驗 Cache 併發 Race 檢測與防禦機制。 |
| `concurrency_005` | Concurrency Suite | Race Condition / Pool | AUTOMATIC | 檢驗 Pool 併發 Race 檢測與防禦機制。 |
| `concurrency_006` | Concurrency Suite | Race Condition / Ordered List | AUTOMATIC | 檢驗 Ordered List 併發 Race 檢測與防禦機制。 |
| `concurrency_007` | Concurrency Suite | Race Condition / PubSub | AUTOMATIC | 檢驗 PubSub 併發 Race 檢測與防禦機制。 |
| `concurrency_008` | Concurrency Suite | Race Condition / Transaction | AUTOMATIC | 檢驗 Transaction 併發 Race 檢測與防禦機制。 |
| `evidence_gap_001` | Local Heal Gap Suite | Evidence Graph Mismatch | AUTOMATIC | 驗證 Evidence Graph 缺失檔案風險偵測邏輯。 |
| `action_protocol_001` | Local Heal Gap Suite | Fuzzy Patch Protocol | AUTOMATIC | 驗證 Fuzzy-only patch fail-closed 協議防禦。 |
| `verifier_gap_001` | Local Heal Gap Suite | False Success Search Mismatch | AUTOMATIC | 驗證 Search Mismatch 時防止 False Success 之保護。 |

* **排除任務數量 (Excluded count)**: 11 個任務。
* **排除原因類別 (Exclusion classes)**:
  * `EXTERNAL_REPO_REQUIRED` (10 個任務，需要外部 SWE-bench 倉庫代碼)。
  * `MISSING_FIXTURE` (1 個任務，缺少 `concurrency_003` 測試固件)。

---

## 3. 實體路由執行結果與證據 (AW2)

所有 12 個任務均已完成實體 rerun，產出 trace.json, receipt.json, verifier_result.json, learning_result.json 及 model_or_route_result.json，並保存在 [tasks/<task_id>/](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/aw_executable_subset_ceiling_v0/tasks/) 中。

### 解決率與驗證狀態
* **12/12 任務均通過 (PASS)** 且 `tests_executed` > 0。
* 任務無任何硬編碼 (Hardcoded expected patches) 或 `task_id` 特異性繞過邏輯。
* 所有任務之驗證均經由 `pytest` 實體執行並完成 verification 驗證，拒絕僅憑 receipt 宣稱成功 (Receipt-only success)。

---

## 4. 基準對照分析 (AW3)

經審查，本次可執行子集與現存基準的對照結果已記錄於 [baseline_comparison.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/aw_executable_subset_ceiling_v0/baseline_comparison.json)：

* **可比基準可用性 (comparable_baseline_available)**: `false`
* **基準任務重疊 (baseline_task_overlap)**: 2 個任務 (`C_12481` 與 `C_13453`)。
* **無法直接對照原因**: AS-R 階段中僅有 2 個 overlapping 任務處於可執行狀態，其餘 10 個任務（concurrency 與 gap 任務）在 AS-R 當時尚未被 restored (skipped/unavailable)。
* **對照結論**: 為維護數據誠信，**不偽造 uplift 提升率**，僅申報可執行子集的絕對解決率 (Absolute performance)。

---

## 5. 能力啟用與影響審計 (AW4)

對於 12 個任務和 12 大能力之啟用狀態與決策影響，已完成精準審計並記錄於 [capability_activation_matrix.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/aw_executable_subset_ceiling_v0/capability_activation_matrix.json) 中。

### 能力統計摘要
* **追蹤之能力總數**: 12
* **子集內總調用次數**: 38 次
* **影響決策分類**:
  * **C-Track 任務 (`C_12481` / `C_13453`)**: 啟用並調用全部 12 大能力。其中：
    * `Sandbox / Regression Guard`、`ClaimDeliveryGate` 展現 **SAFETY_INFLUENTIAL** (保護執行沙箱與 commit 驗證)。
    * `Qwen 7B`, `DeepSeek 6.7B`, `Evidence Graph`, `Deterministic Applier` 展現 **DECISION_INFLUENTIAL** (影響模型與路由決策)。
    * `MemoryRetrievalAdapter`, `Autoreason Advisory`, `Belief Trace` 展現 **TRUST_INFLUENTIAL** (影響信賴等級評估)。
  * **併發與 Gap 任務**: 為了防止本地小模型代價與不穩定性 (prevent cost and flake)，這些確定性迴歸任務採取 LLM 旁路設計 (`SKIPPED_WITH_REASON`)，但全部調用並執行了 `Sandbox / Regression Guard` (具備 **SAFETY_INFLUENTIAL** 影響，經 pytest 實體沙箱運行驗證)。

---

## 6. 邊界與宣稱誠信核對 (AW5)

我們對所有合規指標進行了嚴格核對，並記錄於 [boundary_and_claim_integrity.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/aw_executable_subset_ceiling_v0/boundary_and_claim_integrity.json)：

1. **無公開宣稱 (No public claim)**: `PASS`
2. **無生產發布 (No production release)**: `PASS`
3. **無訓練數據導出 (No training export)**: `PASS`
4. **內部專用 (Internal only)**: `PASS`
5. **無 receipt-only 假解決**: `PASS` (每個 solved 任務皆有 pytest 實體 PASS 證據)
6. **無硬編碼補丁 (No hardcoded patch)**: `PASS`
7. **無 task_id 捷徑邏輯**: `PASS`
8. **排除任務不計入 solved**: `PASS`
9. **不推廣至原 35 任務 Ceiling**: `PASS`

---

## 7. 最終決策與下一步建議 (AW6)

基於 12/12 實體任務全數通過、數據完全可信、能力調用鏈條完整：

* **決策 verdict**: `AW6_EXECUTABLE_SUBSET_CEILING_CONFIRMED`
* **後續建議**: 
  * 建議啟動 **AX 軌跡**，針對排除的 11 個 `EXTERNAL_REPO_REQUIRED`/`MISSING_FIXTURE` 任務進行 Root-Cause 分析與排除阻礙。
  * 建議啟動 **AY 軌跡**，進一步擴大可執行自動化任務包 (Broaden executable pack)。
