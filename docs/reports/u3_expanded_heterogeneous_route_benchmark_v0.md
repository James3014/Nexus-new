# U3 — Expanded Heterogeneous Route Benchmark

**狀態**: `U3_HETEROGENEOUS_ROUTE_REAL_REPAIR_UPLIFT_CONFIRMED`, `U3_DEEPSEEK_SECOND_PROPOSER_CONFIRMED`, `U3_3B_JUDGE_SOFT_GATE_CONFIRMED`  
**評估日期**: 2026-06-21  
**任務集**: 12 個已分類任務 (8 題真實修補/回歸任務, 4 題驗證任務)  
**對照路由**: Route A, B, C, D

---

## 1. 任務加權與通過率分析 (`task_class_weighted_summary.json`)

我們對擴展後的 12 個任務進行了加權評估（真實修復權重為 0.7，驗證任務權重為 0.2）：
$$\text{WeightedScore} = 0.7 \cdot \text{RealRepairRate} + 0.2 \cdot \text{VerificationRate}$$

各路由的加權綜合得分如下：

| 路由 ID / 名稱 | 真實修復率 (8 題) | 驗證任務率 (4 題) | 綜合加權得分 | 判定與結論 |
| :--- | :---: | :---: | :---: | :--- |
| **Route A** (single_7b) | 25.0% (2/8) | 100% (4/4) | **0.3750** | FAIL (真實修補大部分失敗) |
| **Route B** (dual_proposer) | 100% (8/8) | 100% (4/4) | **0.9000** | **PASS** (異質提案極具優勢) |
| **Route C** (judge_plus_dual) | **100% (8/8)** | **100% (4/4)** | **0.9000** | **PASS (最優加固路由推薦)** |
| **Route D** (fallback_14b) | 0.0% (Blocked) | 0.0% (Blocked) | **0.0000** | **BLOCKED** (Resource Gated) |

---

## 2. 核心指標與審計發現

1.  **實體修復能力真實躍升 (Real Repair Uplift Confirmed)**:
    - 面對擴展後的 8 個真實代碼修復任務，單一 Qwen 7B 路由 (Route A) 僅能修復 2 題（成功率 **25%**，僅通過 `astropy-13236` 與 `sympy-13031`）。
    - 而 **Route C (3B Judge + Dual Proposer)** 成功解決了全部 8 題實體修復任務 (通過率 **100%**)，在真實代碼修復能力上實現了重大突破。
2.  **Challenger 獨特貢獻 (Second Proposer Confirmed)**:
    - 數據顯示，`deepseek-coder:6.7b-instruct` 在面對 Qwen 7B 失敗的困難置換問題（如 `C_12481` 循環構造）與 `django-11001` 正則表達式錯誤時，產出了獨特修復提案（DeepSeek Unique Wins = 2）。兩者互補，在 deterministic scoring 下順利由 Verifier 收口。
3.  **收據完整性檢驗 (`receipt_completeness.json`)**:
    - 通過對實體產出 receipt 的靜態檢查，Route C 在每次手動執行中產出的 `final_receipt.json` 完全符合 **21 個 required 欄位**約束，沒有任何資料缺失，具備完備的控制流可審計性。
