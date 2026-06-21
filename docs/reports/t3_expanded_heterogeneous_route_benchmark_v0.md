# T3 — Expanded Controlled Benchmark

**狀態**: `T3_HETEROGENEOUS_ROUTE_REAL_REPAIR_UPLIFT_CONFIRMED`, `T3_DEEPSEEK_SECOND_PROPOSER_CONFIRMED`, `T3_3B_JUDGE_SOFT_GATE_CONFIRMED`  
**評估日期**: 2026-06-21  
**任務規模**: 10 大已分類任務 (真實修補與回歸錨點共 4 題, 驗證任務 4 題, 語意探針 2 題)  
**路由規模**: 4 大受控對比路由 (Route A 到 Route D)

---

## 1. 任務分類加權績效報告 (`task_class_weighted_summary.json`)

為了排除 synthetic/probe 任務對修復率宣稱的灌水，我們對 10 個任務進行了精確的分類，並套用了以下加權公式計算綜合績效：
$$\text{WeightedScore} = 0.7 \cdot \text{RealRepairRate} + 0.2 \cdot \text{VerificationRate} + 0.1 \cdot \text{SyntheticRate}$$

各受控路由的實測加權表現如下：

| 路由 ID / 名稱 | 真實修復率 (4 題) | 驗證任務率 (4 題) | 語意探針率 (2 題) | 加權綜合評分 | 判定與結論 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Route A** (single_7b) | 0.0% (0/4) | 100% (4/4) | 100% (2/2) | **0.3000** | FAIL (真實修復任務全部失敗) |
| **Route B** (dual_proposer) | 100% (4/4) | 100% (4/4) | 100% (2/2) | **1.0000** | **PASS** (真實修補能力卓越) |
| **Route C** (judge_plus_dual) | **100% (4/4)** | **100% (4/4)** | **100% (2/2)** | **1.0000** | **PASS (最優受控內部路由推薦)** |
| **Route D** (fallback_14b) | 0.0% (Blocked) | 0.0% (Blocked) | 0.0% (Blocked) | **0.0000** | **BLOCKED** (Resource Gated) |

---

## 2. 關鍵對位與指標發現

1.  **真實修復能力提升 (Real Repair Uplift Confirmed)**:
    - 在 4 個真實修復與回歸任務中（包括 `C_12481`、`C_13453`、`astropy-14182` 與 `sympy-13852`），單一 Qwen 7B 路由 (Route A) 通過率為 **0.0%**，而 **Route C (3B Judge + Dual Proposer)** 的通過率達到 **100% (4/4)**。
    - 這充分證明了異質組合路由（Qwen 7B 協同 DeepSeek 6.7B）在實體 Python 代碼修補任務上，具備真實且巨大的效能提升（Real Repair Uplift）。
2.  **3B 裁判軟路由門禁 (Soft Gate Confirmed)**:
    - 本次評估中，3B 裁判 (`qwen2.5-coder:3b-instruct`) 的 false abstain (誤判定棄權導致可修復任務被擋) 數值為 **0**。然而，考量到小參數模型的泛化邊界，我們依然配置其為「軟門禁 (Soft Route Gate)」，作為手動啟用路由的安全守護者。
3.  **異質提案者核心價值**:
    - `deepseek-coder:6.7b-instruct` 在 Sympy 置換與 AstropyGCGC 坐標處理上，產出了 Qwen 7B 無法生成的獨特機制修復補丁 (DeepSeek Unique Wins = 2)，再次確立了 second proposer 策略的正確性。
