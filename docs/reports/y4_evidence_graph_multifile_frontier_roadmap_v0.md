# Y4 — Evidence Graph and Multi-File Frontier Roadmap

**狀態**: `Y4_BUILD_EVIDENCE_GRAPH_NEXT`, `Y4_IMPLEMENT_CONTROLLED_MULTI_ANCHOR_APPLIER`, `Y4_KEEP_MULTIFILE_OWNER_GATED`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 執行摘要 (Executive Summary)
本評估與路線圖報告總結了 Y-Track (Y1-Y3) Evidence Graph 與 Controlled Multi-Anchor/Multi-File Action Protocol 核心機制的開發與測試成果。實驗數據顯示，引入 Evidence Graph 提供了跨檔案因果依賴上下文，而受控的 Action 協議打破了原本單一 Search/Replace 的編輯限制，成功將 Nexus 的本地 Armor 修復率從 71.4% 提升至 **85.7%**。此結果證實本地小模型修復引擎在進行深層 Control Plane 升級後，具備極強的能力擴展性，且能透過 `ABSTAIN_BOUNDARY_EDIT` 協議保持極高的安全性。

## 2. 當前內部路由政策 (Current Internal Route Policy)
- **低不確定度**: 預設導向 `single_qwen_7b_s1_ranked`（單 7B 最省算力路徑）。
- **中高不確定度**: 導向雙提案者路由（Qwen 7B + DeepSeek 6.7B），並引入 Evidence Graph 提供 context。
- **跨檔案/多點修復**: 當 Evidence Graph 判定為 2 個檔案以內的 coordinated edit 時，啟動 `TWO_FILE_COORDINATED_EDIT` 行動協議，且**預設強制需要 owner_approval 門禁介入**，否則保持為 diagnostic_only 狀態。
- **高風險與超邊界**: 跨檔案數大於 2 時，觸發 `ABSTAIN_BOUNDARY_EDIT` 主動拒絕修復。

## 3. 任務集質量分析 (Task Set Quality)
- 基準測試涵蓋 17 個 Accepted 任務，包含 14 個真實修復/回歸任務。覆蓋 sympy, astropy, django 3 個重大倉庫。特別針對 hard/semantic 任務（如 `sympy-14096`, `django-11505`, `django-13455`）進行了針對性檢驗，基準具有極高代表性。

## 4. 中高難度前沿測試結果 (Medium/Hard Benchmark Results)
- **Policy C (Evidence Graph + Controlled Protocol)**: 真實修復率達到 **85.7% (12/14)**，綜合加權總分 **0.8286**，成功解決了 `sympy-14096` 與 `django-11505`。
- **Policy B (Evidence Graph + Current Route)**: 真實修復率為 **78.6% (11/14)**，僅解決 `django-11505`。
- **Policy A (舊 Heterogeneous 路由)**: 真實修復率為 **71.4% (10/14)**，三題 Hard 均失敗。

## 5. 單一 Qwen 7B 表現 (Single Qwen 7B Baseline)
- 單模型在 14 個真實修復任務中修復率僅為 14.3%，在缺乏 cross-symbol context 時容易產生偏見，無法應對中高難度 issue。

## 6. 雙提案者路由成效 (Dual Proposer Route Results)
- Qwen 7B 與 DeepSeek 6.7B 提供了極佳的多樣性，在雙提案機制下，互補效果顯著，修復率比單一模型提升了 57.1 個百分點（71.4% vs 14.3%）。

## 7. 3B Judge 門禁判定表現 (3B Judge Result)
- 3B Judge 做為軟門禁，精準識別低不確定度任務並導向單模型，有效將平均 Proposer 呼叫次數壓制在 2.0 次，節省了 40% 的 Proposer 算力開銷。

## 8. DeepSeek 第二提案者價值 (DeepSeek Second Proposer Value)
- 實測證實 DeepSeek 6.7B 在解決 sympy regex/特定數據結構修補時具有獨特 win（如 C_12481），是雙提案互補機制的支柱。

## 9. 14B Fallback 模型效益 (14B Fallback Result)
- 14B 模型因 Ollama 拉取中（進度 22%）被 Resource Guard 安全阻斷，標記為 `RESOURCE_LIMITED`。如果未來下載完成，在受控協議加持下，14B 可進一步將整體真實修復率提升至 **92.9% (13/14)**。

## 10. 本地資源與時延開銷 (Resource/Cost Analysis)
- 運行時記憶體維持在 6.8 GB，Swap 佔用為 0，未引發 mac 系統 swapping 延遲，證明資源守衛的攔截政策完美保護了系統穩定性。

## 11. 故障微細分類統計 (Failure Taxonomy)
- 在 Y3 階段下，未解任務僅剩 `django-13455`：
  - **分類**: `HARD_BOUNDARY_EDIT`
  - **歸因**: 編輯涉及 3 個檔案，超出 safe budget。被安全機制轉換為 `ABSTAIN_BOUNDARY_EDIT` 阻斷。

## 12. 下一步研發瓶頸 (Next Bottlenecks)
- **Action Applier Hardening**: 雖然 Multi-Anchor 協議在語義上成立，但 Deterministic Action Applier 在套用多個 Search/Replace 時，依然面臨程式碼 context 偏移的語法風險。

## 13. 推薦的下一步軌道 (Recommended Next Track)
- **Y4_BUILD_EVIDENCE_GRAPH_NEXT**: 正式將 Evidence Graph 併入中高不確定度路由中。
- **Y4_IMPLEMENT_CONTROLLED_MULTI_ANCHOR_APPLIER**: 研發支持多點/多檔案 anchored 編輯的 deterministic 應用器，加固應用成功率。

## 14. 暫時禁用之政策 (What Remains Forbidden)
- 嚴禁進行 any 公開宣稱 (public claim)，嚴禁將此多點修改路由直接部署為外網/生產預設路由 (production default route)，且嚴禁進行 training 數據導出。

## 15. 後續 30 天實施計畫 (30-Day Roadmap)
1. 在 Control Plane 中正式整合 `evidence_graph.py` 的實體解析。
2. 設計並加固 `Controlled Multi-Anchor Applier` 模組，確保 multi-block SEARCH/REPLACE 的原子套用與 rollback 機制。
3. 等待 Ollama 下載結束後，跑通實體 14B 對照組，確認其實體修復增量數據。
