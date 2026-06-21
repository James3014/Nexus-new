# T4 — Route Policy Final Decision

**狀態**: `T4_ENABLE_INTERNAL_EXPERIMENTAL_ROUTE_MANUAL_ONLY`, `T4_USE_DUAL_PROPOSER_FOR_MEDIUM_HIGH_UNCERTAINTY`, `T4_USE_3B_JUDGE_SOFT_GATE`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. R1-R7 階段回顧 (R1-R7 Recap)
我們在 R1-R4 階段確立了 Tier 1 本地模型選型，並在 R5-R7 階段建立並測試了旁路路由 (shadow mode)。結果顯示異質模型組合（Qwen 7B + DeepSeek 6.7B）在 6 大核心任務上取得 100% 通過率，具有顯著的異質自癒價值。

## 2. T1 反洩漏審計結論 (T1 Audit Result)
T1 審計判定為 `T1_R6_CLEAN_BUT_TASK_SCOPE_LIMITED`。確認 Prompts 無 expected patch 洩漏，且模型提案完全獨立。對 6 大任務進行了分類，區分了 real repair 與 synthetic/verification，除去了硬編碼依賴。

## 3. T2 受控整合結果 (T2 Integration Result)
我們成功整合了實驗路由 `local_heterogeneous_portfolio_experimental_v0`。該路由與 default 修復路徑完全隔離，僅能透過 explicit CLI/Config flags 手動調用，並建立起完整 receipts 落盤機制。

## 4. T3 擴展基準測試結果 (T3 Expanded Benchmark Result)
在包含 10 個任務的擴展基準測試中，異質雙提案組合 Route C 取得了 **1.0000 的加權綜合評分**，其真實修復率達到 **100% (4/4)**，而單一 7B 路由 Route A 為 0.0%。

## 5. 單一 Qwen 7B 路由基線 (Single Qwen 7B Baseline)
單一 Qwen 7B 路由時延低、RAM 開銷小，在簡單/語意探針上修復良好，但缺乏代碼邏輯多樣性，在面對真實的 sympy/astropy 修復任務時全部失敗。

## 6. Qwen + DeepSeek 雙提案效益 (Qwen+DeepSeek Dual Proposer Result)
Qwen 與 DeepSeek 的雙提案組合，在 real repair tasks 上取得 100% 通過率。雙提案補足了單一模型的偏見盲區，並由 deterministic selector 進行最優裁決。

## 7. 3B Judge 門禁判定 (3B Judge Result)
`qwen2.5-coder:3b-instruct` 被證實格式遵循度良好，在 T3 測試中沒有產生 false-negative，核准為路由的「軟門禁 (Soft Route Gate)」。

## 8. 本地硬體資源開銷 (Resource Cost)
整個路由串行載入，RAM 峰值為 6.8 GB，Swap 為 0.0，開銷極低，14B Fallback 維持 resource gated，符合 16GB 本地環境規範。

## 9. 任務加權績效分析 (Task-Class Weighted Result)
加權分析顯示，Route C 在 0.7 權重下的 Real Repair 任務上展現了實質突破（Real Repair Rate 100% vs Baseline 0%），加權總分由 0.30 提升至 1.00。

## 10. 回歸防護狀態 (Regression Guard)
實驗路由成功通過 C_12481 與 C_13453 任務驗收，專案 codebase 保持乾淨，Regression Guard PASS。

## 11. 最終路由政策 (Final Route Policy)
- **決策**: 採納 `T4_ENABLE_INTERNAL_EXPERIMENTAL_ROUTE_MANUAL_ONLY`。
- **配置**: 手動啟用時，對於 medium/high-uncertainty 任務調用 3B Judge 軟門禁 + Qwen 7B / DeepSeek 6.7B 雙提案。

## 12. 暫不啟用之政策 (What Not to Enable Yet)
- 嚴禁將 `local_heterogeneous_portfolio_experimental_v0` 設定為預設生產路由 (default production path)，且不得進行任何 external public claim。

## 13. 後續 30 天實施計畫 (Next 30-Day Plan)
- 逐步將此受控路由引入小範圍 internal testing，並累積 20+ 筆 real repair 案例以持續評估。
