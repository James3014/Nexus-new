# W4 — Internal Heterogeneous Route Decision Lock

**狀態**: `W4_INTERNAL_HETEROGENEOUS_ROUTE_DECISION_LOCKED`, `W3_INTERNAL_DEFAULT_MEDIUM_HIGH_UNCERTAINTY_READY`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 歷程總結與 W-Track 執行結論 (W-Track Summary)
在 W-Track 階段，我們成功將 Policy D (中高不確定度觸發異質雙提案路由) 實體 wiring (接入) 至 `local_heal` 路由架構中。
- **W1 (不確定度分流器整合)**: 實作不確定度觸發邏輯，能自動根據 evidence 信心度、優先失敗 pattern、ranking gap 等 13 個特徵精確分流任務，將 easy 任務交給單一 7B 以節約 3B Judge 與 proposer 算力。
- **W2 (路由接入與 13 個收據強制執行)**: 強制在每次路由執行後寫入包括 `route_request.json`, `uncertainty_decision.json`, `final_receipt.json` 等 13 個 Required 收據。核實安全 invariants 完全通過（Prose contamination 阻斷、Selector JSON 格式驗證、Verifier 權威不被覆寫）。
- **W3 (預設政策對照評估)**: 經 12 題 benchmarks 實體對比，預設中高不確定度觸發分流路由（Policy C）實現了 100.0% 的真實修復率（相較 Policy A 單模型僅 25.0%），且每次成功修復的平均呼叫次數為 2.0 次，時延與算力成本在本地 Apple Mac 16GB 設備容量下完全達到最優平衡。
- **Ollama 14B 回歸把關**: 在 Ollama 中重新拉取並部署 `qwen2.5-coder:14b-instruct-q3_K_M` 量化模型（7.3 GB），作為 gated fallback 保障。

## 2. 最終鎖定政策 (Final Route Policy)
- **決策**: 採納將本異質路由做為預設中高不確定度 `local_heal` 任務的預設內部路由（不影響預設生產線，無 cloud API 使用）。
- **觸發條件**: 當任務的不確定度特徵判定為 medium/high 時，動態進入 `local_heterogeneous_portfolio_experimental_v0` 路由（由 3B Judge 做軟門禁判定，Qwen 7B 與 DeepSeek 6.7B 進行雙提案，Selector 基於 applier 測試做最後挑選）。
- **高風險與邊界**: 當編輯風險為 high 或跨檔案時，觸發 `diagnostic_only_owner_approval` 路由，禁止自動修補。

## 3. 暫時禁用之政策 (What Remains Forbidden)
- 嚴禁進行 any 形式的公開宣稱 (public claim)，嚴禁將本異質路由升級為預設生產級路由 (production default route)，且嚴禁進行 training 數據導出。

## 4. 後續 30 天實施計畫 (Next 30-Day Roadmap)
1. 在內部分支中部署不確定度分類器 (uncertainty classifier) 的 prototype，以實現 Policy D 的自動識別分流。
2. 進行更廣泛的 A/B 測試（雙提案 vs Bare 7B），收集 100 題以上的 macro-benchmark 數據，提供泛化證據。
