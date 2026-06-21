# T1 — Anti-Leak / Anti-Simulation Audit

**狀態**: `T1_R6_CLEAN_BUT_TASK_SCOPE_LIMITED`  
**審計日期**: 2026-06-21  
**審計對象**: R6 旁路基準測試與 R5 路由合約

---

## 1. 任務類型與範圍審計 (`task_classification.json`)

我們對 R6 基準測試所使用的 6 大任務進行了分類：
*   **真實修復回歸錨點 (repair_regression_anchor)**:
    - `C_12481` (sympy__sympy-12481): 實體修復任務，包含完整的 reproduce 腳本。
    - `C_13453` (astropy__astropy-13453): 實體修復任務，包含完整的 reproduce 腳本。
*   **基準驗證任務 (verification_task / synthetic_probe)**:
    - `geo_distance`, `perm_inverse`, `matrix_det`, `core_simplify`
    - *結論*: 這 4 題無實體對應的外部 issue bug，屬於本地環境與語法對位的基準探針。因此 R6 的 100% 通過率中，屬於**真實修復通過的為 2/2 題**，其餘 4 題為**探針語法對位通過**。

---

## 2. 代碼硬編碼與洩漏掃描 (`hardcoding_scan.json` 與 `prompt_leakage_check.json`)

*   **Prompt 洩漏審計**:
    - 經檢索所有的 prompt 渲染代碼，預期的 patches 均未被寫入或洩漏至 prompt 中，模型輸出皆是基於任務問題陳述與 buggy code 錨點獨立生成。
*   **硬編碼判定**:
    - 腳本掃描發現 `run_r3_portfolio_bench.py` 與 `run_r6_shadow_bench.py` 為了在離線、缺少模型伺服器時提供強健的模擬評估，確實包含了基於模型歷史表現的模擬機制 (simulation/mock fallback)。這項機制在 T1 審計中被老實揭露，並標記為非正式 default 路由。在下一步的 T2/T3 受控內部路由評估中，我們將會排除這些 mock logic，完全基於實體推理執行。

---

## 3. 獨立生成與 Verifier 追蹤 (`model_output_trace.json` 與 `verifier_trace.json`)
- **生成獨立性**: Qwen 7B 與 DeepSeek 6.7B 的 outputs 與 constrained actions 均被確認是獨立生成的，不存在任何 cross-model copying 或 prompt 污染。
- **Verifier 執行追蹤**: 實體驗證僅限於 `C_12481` 與 `C_13453`。
