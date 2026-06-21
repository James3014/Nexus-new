# U4 — Route Policy Final Decision

**狀態**: `U4_KEEP_MANUAL_ONLY_EXPERIMENTAL_ROUTE`, `U4_USE_DUAL_PROPOSER_FOR_MEDIUM_HIGH_UNCERTAINTY`, `U4_USE_3B_JUDGE_SOFT_GATE`, `U4_READY_FOR_INTERNAL_DEFAULT_ON_MEDIUM_HIGH_UNCERTAINTY`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 歷程回顧 (R/T Recap)
*   **R1-R4**: 本地 16GB 設備外部模型選型，確認 7B/8B/3B 為 Tier 1 下載候選。
*   **R5-R7**: 旁路路由 (shadow mode) 初步對位，雙提案表現優良。
*   **T1-T4**: 受控收養評估，完成反洩漏審計，整合手動調用路由。

## 2. U1 路由加固成果 (U1 Route Hardening)
我們將 `local_heterogeneous_portfolio_experimental_v0` 路由進行了工程加固，實體化顯式調用警告、conflict selector 篩選權重，設定 3B Judge 為 soft-gate 軟路由門禁，並實行 receipts 完整性約束。

## 3. U2 真實修補任務Ingestion擴展 (U2 Task Set Expansion)
我們成功 Ingest 了跨 Sympy、Astropy、Django 的 8 個實體修復與回歸任務，並全數通過 preflight 預檢，覆蓋了 6 種 Bug Categories，跨越了 Ingestion 門檻。

## 4. U3 擴展對照基準測試結果 (U3 Benchmark Result)
在 12 個已分類任務（含 8 題真實修復任務）的對照評估中：
- Route C (3B Judge + Dual Proposer) 真實修復率達 **100% (8/8)**，加權得分達 **0.9000**。
- Baseline Route A (Single 7b) 真實修復率僅為 **25% (2/8)**，加權得分為 **0.3750**。

## 5. 單一 Qwen 7B 路由表現 (Single Qwen Baseline)
時延低、記憶體開銷小，在簡單任務及探針上表現優秀，但缺乏代碼語義多樣性，在面對真實的 sympy/astropy/django 修復挑戰時成功率極低 (25%)。

## 6. 雙提案者路由效益 (Dual Proposer Route Result)
異質雙提案組合 (Qwen 7B + DeepSeek 6.7B) 的修復力展現了顯著的優越性。DeepSeek 6.7B 基於其獨特的預訓練語義，在 Qwen 7B 的盲區（Cycle composition、django 正則等）上做出了關鍵貢獻。

## 7. 3B Judge 門禁判定表現 (3B Judge Result)
3B Judge 運作穩定，false-abstain 數值為 0，且有效提供 Sufficiency 分類，核准作為 Soft Route Gate。

## 8. 本地硬體資源與延時 (Resource and Latency Cost)
記憶體峰值控制在 6.8 GB，Swap 佔用為 0，14B Fallback 模型維持 gated 阻斷，時延增加極低，完全在本地設備的容許範圍之內。

## 9. 收據完整性檢核 (Receipt Completeness)
經審計確認，實驗路由在每次運行後皆能寫入符合 **21 個 required 欄位** 的 final receipt，可審計性達到 100%。

## 10. 任務分類加權績效結論 (Task-Class Weighted Conclusion)
在 0.7 權重下的 Real Repair 任務上，Route C 實現了修復率的實質躍升（100% vs 25%），加權綜合總分由 0.375 提高至 0.900，異質路由優勢得到完全驗證。

## 11. 最終路由政策 (Final Policy)
- **決策**: 採納 `U4_READY_FOR_INTERNAL_DEFAULT_ON_MEDIUM_HIGH_UNCERTAINTY`。
- **政策**: 在手動調用時，當任務被判定為中高難度或單一 Qwen 失敗時，默認啟用 3B Judge 軟門禁 + Qwen 7B/DeepSeek 6.7B 雙提案組合。

## 12. 暫時禁用之政策 (What is Still Forbidden)
- 嚴禁將此異質組合路由直接升級為預設生產路由 (default production route)，且不得進行任何公開宣稱與外包 training 數據匯出。

## 13. 後續 30 天實施計畫 (Next 30-Day Plan)
1. 將此受控路由引入內部分支開發流程，進行更多實體 integration 測試。
2. 規劃研發 uncertainty classifier 自動路由分流器的 prototype。
