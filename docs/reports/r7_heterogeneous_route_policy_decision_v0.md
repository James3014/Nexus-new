# R7 — Route Policy Decision

**狀態**: `R7_ADOPT_QWEN_DEEPSEEK_DUAL_PROPOSER_INTERNAL`, `R7_USE_DUAL_PROPOSER_FOR_MEDIUM_HIGH_UNCERTAINTY`, `R7_USE_3B_JUDGE_ROUTE_GATE`, `R7_USE_14B_RESOURCE_GATED_FALLBACK`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. R1-R4 成果回顧 (R1-R4 Recap)
在 R1-R4 階段中，我們在本地 16GB RAM 硬體限制下分析了異質模型可行性。Qwen 7B (Proposer)、DeepSeek 6.7B (Challenger)、Granite 8B (Critic)、3B Coder (Judge) 被選為 Tier 1 候選。初步微基準測試與基準測試驗證了同質 Qwen 7B 的同質 bias，推翻了「多模型不值得」的偏見，證實了異質提案在複雜機制對位上的潛力。

## 2. R5 Shadow 路由設計 (R5 Shadow Route Design)
我們設計了旁路路由 `local_heterogeneous_portfolio_shadow_v0`，串接 3B Judge 做 Sufficiency 分類，並在 Yes 時並行由 Qwen 7B 與 DeepSeek 6.7B 提出 constrained JSON action，由 Nexus Deterministic Selector (評分機制) 做首選判定，最後送交實體 Verifier。

## 3. R6 Shadow 基準測試結果 (R6 Benchmark Results)
對照測試顯示，Route C (3B Judge + Dual Proposer) 在 6 大任務（C_12481, C_13453, geo_distance, perm_inverse, matrix_det, core_simplify）上取得 **100% (6/6)** 通過率，而 Route A (Single 7B) 僅為 66.7%。

## 4. 單模型 7B 基線評估 (Single 7B Baseline)
單一 Qwen 7B 在簡單與 verification 任務上表現良好，但對於複雜邏輯修復（如 sympy Cycle composition），由於欠缺機制多樣性，在重複提案中持續發生語義偏差（失敗率 33.3%）。

## 5. Qwen + DeepSeek 雙提案結果 (Qwen+DeepSeek Dual-Proposer Results)
雙提案路由解決了單模型的盲區。DeepSeek Coder 在代碼機制上有極強的直覺，與 Qwen Coder 產生完美的語義互補，且雙提案通過 deterministic scoring 篩選，無需多數決或討論。

## 6. 3B Judge 實用性判定 (3B Judge Utility)
`qwen2.5-coder:3b-instruct` 在 JSON 格式與證據充分性判定上表現可靠，將其作為門禁守門人 (Route Gate)，可於 proposer 推理前成功過濾資訊不足之任務，防止無效算力浪費。

## 7. 14B Fallback 可行性 (14B Fallback Feasibility)
`qwen2.5-coder:14b-instruct` 僅可在 Resource Guard 動態確認 RAM 充足時冷啟動加載，目前 16GB 硬體限制下暫時禁用，禁止 CPU-only 推理。

## 8. 資源與成本評估 (Resource Cost)
Route C 異質雙模型串行調用之峰值 RAM 佔用為 6.8 GB，Swap 佔用為 0，整體時延增加在 50ms-100ms 之內，成本完全在本地容忍範圍。

## 9. 回歸防護狀態 (Regression Guard)
R5/R6 旁路路由在實體執行上，成功通過 C_12481 與 C_13453 任務，且未對原有 src 進行任何破壞，Regression Guard PASS。

## 10. 推薦路由政策 (Recommended Route Policy)
- **政策**: 採納 **Option 3** (Use Qwen+DeepSeek only for medium/high uncertainty tasks) 搭配 **Option 5** (Use 3B Judge as route gate) 暨 **Option 6** (Use 14B fallback only after dual proposer fails)。
- **理由**: 對於低複雜度之 verification/simple 任務，採用單一 Qwen 7B 路由以節省 token 與時延開銷；對於中/高複雜度或 Qwen 失敗之修補任務，啟用 3B Judge 守門並加載 Qwen 7B + DeepSeek 6.7B 異質雙提案組合。

## 11. 暫不啟用之政策 (What Not to Enable Yet)
- 暫不啟用任何 public claim 與對外生產路由，所有異質路由僅維持在內部開發 (internal-only) 與 shadow mode 評估階段，嚴禁直接晉升為 default routing 進行生產修復。
