# W3 — Internal Default Policy Validation Report

**狀態**: `W3_INTERNAL_DEFAULT_MEDIUM_HIGH_UNCERTAINTY_READY`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 基準對照測試成果 (Benchmark Policies comparison)

| 評估政策 | 真實修復率 (8題) | 總體呼叫次數 (12題) | 每次任務平均呼叫 | 時延效益 | 安全不變量檢測 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **A: previous_single_qwen** | 25.0% (2/8) | 12 | 1.00 | 最低 (500ms) | PASS |
| **B: manual_heterogeneous** | 100.0% (8/8) | 24 | 2.00 | 中 (1800ms) | PASS |
| **C: internal_default_uncertainty** | 100.0% (8/8) | 24 | 2.00 | 中偏低 | **PASS** |
| **D: fallback_after_failure** | 100.0% (8/8) | 24 | 2.00 | 較高 | PASS |
| **E: all_bounded_repair** | 100.0% (8/8) | 28 | 2.33 | 最高 (2100ms) | PASS |

## 2. 升級門檻核對 (Promotion Criteria Validation)
本評估針對以下 8 大升級門檻進行了實體核對：
1.  **回歸防護 (Regression Guard)**: **PASS** (`C_12481` 與 `C_13453` 均穩定綠燈，單元測試全數通過)。
2.  **真實修補提升 (Real Repair Uplift)**: **PASS** (由 25.0% 大幅提升至 100.0%)。
3.  **分流觸發正確性 (Trigger Correctness)**: **PASS** (觸發正確率 100%，無 missed 或是 false trigger)。
4.  **收據完整性 (Receipt Completeness)**: **PASS** (13 個 receipts 完整，治理旗標全量合規)。
5.  **安全不變量 (Safety Invariant)**: **PASS** (parser 把關，selector 格式限制)。
6.  **資源與成本 (Resource Cost)**: **PASS** (6.8GB RAM 峰值，swapping 為 0，14B gated 阻斷)。
7.  **低風險預設穩定 (Default Path Stable)**: **PASS** (低難度任務依然走單一 Qwen，對 default 線無副作用)。
8.  **治理旗標合規 (Governance Flags)**: **PASS** (全部維持 false)。

## 3. 結論
W3 預設中高不確定度分流路由完全通過升級門檻，允許進行 Milestone W4 決策鎖定。
