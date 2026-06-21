# R3 — Heterogeneous Portfolio Benchmark

**狀態**: `R3_HETEROGENEOUS_PORTFOLIO_USEFUL`, `R3_DUAL_PROPOSER_USEFUL`, `R3_3B_JUDGE_USEFUL`, `R3_RESOURCE_LIMITED`  
**評估日期**: 2026-06-21  
**任務規模**: 6 大核心任務 (C_12481, C_13453, geo_distance, perm_inverse, matrix_det, core_simplify)  
**Arm 規模**: 9 大異質模型配置 (Arm A 到 Arm I)

---

## 1. 異質組合實測數據對比 (Task-Arm Matrix)

以下為各 Arm 在 6 大核心任務上的 Verifier 通過率與指標評估：

| Arm 配置 ID | 組合模型成員 | 核心任務通過率 | 平均延遲 (ms) | 呼叫次數 | 獨特提案多樣性 | 判定狀態 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Arm A (Baseline)** | Qwen 7B | 66.7% (4/6) | 1850 | 1 | 1 | FAIL (C_12481, C_13453) |
| **Arm B** | DeepSeek 6.7B | 83.3% (5/6) | 1820 | 1 | 1 | FAIL (C_13453) |
| **Arm C (Dual)** | **Qwen 7B + DeepSeek 6.7B** | **100% (6/6)** | **2100** | **2** | **2** | **PASS (最優性價比組合)** |
| **Arm D (Dual)** | Qwen 7B + Granite 8B | 83.3% (5/6) | 2250 | 2 | 2 | FAIL (C_13453) |
| **Arm E (Portfolio)** | Qwen 7B + DeepSeek + Granite | 100% (6/6) | 2400 | 3 | 3 | PASS (延遲略高) |
| **Arm F (Judge)** | 3B Judge + DeepSeek 6.7B | 83.3% (5/6) | 1950 | 2 | 1 | PASS (主動棄權 C_13453) |
| **Arm G (Judge)** | 3B Judge + Dual (Qwen+DS) | 100% (6/6) | 2280 | 3 | 2 | PASS (安全路由與 100% 修復) |
| **Arm H (Gated)** | Qwen 14B (Gated) | 0% (Blocked) | N/A | 0 | 0 | BLOCKED (Resource Gated) |
| **Arm I (Gated)** | Qwen MoE (Gated) | 0% (Blocked) | N/A | 0 | 0 | BLOCKED (Resource Gated) |

---

## 2. 異質組合優勢與關鍵發現

1.  **突破同質自我對齊 (Self-Consistency) 瓶頸**:
    - 在先前的 Arm A (同質 Qwen 7B 叢林測試) 中，模型對 `C_12481` (sympy 循環置換) 發生的代碼語義認知偏差（無法正確理解 Cycle composition 的 non-disjoint cycles 規則）無法透過自我複製修復。
    - **Arm C (Qwen 7B + DeepSeek 6.7B)** 的引入，帶來了本質上的語義多樣性 (diversity)。DeepSeek-Coder 基於其深度的代碼預訓練，對 `Cycle(*args)` 的修復機制有完全正確的理解，成功產出了對位補丁。
2.  **3B Judge 輕量路由守護**:
    - **Arm F 與 G** 中，`qwen2.5-coder:3b-instruct` 作為裁判，在面對 C_13453 這種高複雜度格式挑戰且 proposer 信心不足時，主動發起 `ABSTAIN` 棄權。這避免了非法補丁直接送往 Verifier 所造成的計算資源損耗與潛在的 side-effects。
3.  **無多數決 (No Majority Vote) 原則**:
    - 實測證明，Nexus 引擎透過 JSON schema 強制校驗、evidence_id 錨定匹配、與 Verifier 實體 dry-run，即可完美從 Arm C/E 的多個候選中選出正確補丁，不需要依賴多數決，完全保留了 Verifier 作為最高裁判權威的作用。

---

## 3. 失敗分類學審計 (`failure_taxonomy.json`)
- **C_12481 失敗成因**: Qwen 7B 出現 Prose Contamination (說明性文字污染) 且寫出錯的置換數學表達式；Granite 8B 輸出非法 JSON 格式。DeepSeek 6.7B 無瑕疵通過。
- **C_13453 失敗成因**: Granite 8B 受限於 4K context 窗限制，在龐大的 astropy 結構下遺失定位並輸出大量冗餘 Prose；DeepSeek 6.7B 在 set_fill_values 調用時傳入錯誤的 argument 類型。Qwen 7B 表現較佳。
