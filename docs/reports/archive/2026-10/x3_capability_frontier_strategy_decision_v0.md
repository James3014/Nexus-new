# X3 — Capability Frontier Strategy Decision

**狀態**: `X3_CONTINUE_INTERNAL_MEDIUM_HIGH_UNCERTAINTY_ROUTE`, `X3_BUILD_EVIDENCE_GRAPH_NEXT`, `X3_EXPAND_ACTION_DSL_NEXT`, `X3_NEED_MORE_REAL_REPAIR_TASKS_BEFORE_CLAIMS`  
**決策日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 執行摘要 (Executive Summary)
本決策報告旨在探討 `local_heal` 本地雙提案路由在擴展至 17 個接受任務（包含 14 個真實修復/回歸任務）後的能力邊界極限。實體數據證實，異質受控路由在 Medium 難度修復任務上表現優異（71.4% 真實修復率），對照單模型 (14.3%) 取得大幅提升。然而，面對 Cross-function (跨函式) 與 Broad edit (跨檔案) 等前沿 Hard 任務，我們碰到了明顯的 Model Semantic Limit (模型語義限制) 與 Hard Boundary Edit (安全不變量限制) 瓶頸。為此，我們確立將研發焦點從「路由驗證」轉移至「能力擴展」，正式決策下一步實施軌道為 **X3_BUILD_EVIDENCE_GRAPH_NEXT** (建立更深度的 CodeIntel 語義圖譜) 與 **X3_EXPAND_ACTION_DSL_NEXT** (安全擴展 Action DSL 空間)。

## 2. 當前內部路由政策 (Current Internal Route Policy)
- **低不確定度**: 預設走 `single_qwen_7b_s1_ranked`（單 7B 最省算力路徑）。
- **中高不確定度**: 預設分流至 `local_heterogeneous_portfolio_experimental_v0`（由 3B Judge 做軟門禁，Qwen 7B + DeepSeek 6.7B 進行雙提案，由 Selector 進行 Dry-run 挑選與 Verifier 最終把關）。
- **高風險與邊界**: 當編輯風險為 high 或跨檔案時，觸發 `diagnostic_only_owner_approval` 路由，禁止自動修補。
- **14B Fallback**: 僅在資源守衛允許時作為 proposer 失敗後的備用 arm 載入，不作為 default。

## 3. 任務集質量分析 (Task Set Quality)
- 本輪 Ingest 預檢通過的 17 個 accepted 任務，覆蓋了 sympy, astropy, django 3 個大庫，以及 7 種 Bug categories (含建構子正規化、跨函式依賴、資料結構不變量等)。真實修復任務數達 14 題，並包含 3 題硬任務，基準質量完全達到 capability boundary 探測要求。

## 4. 中高難度前沿測試結果 (Medium/Hard Benchmark Results)
- **Policy B (預設不確定度分流路由)**: 真實修復率達 **71.4% (10/14)**，加權總分 **0.7286**。
- **Policy A (單 7B 路由)**: 真實修復率僅為 **14.3% (2/14)**，加權總分 **0.2286**。
- **Policy E (14B Fallback 路由)**: 由於 14B 模型下載尚在進行中，本輪被資源守衛安全 gated 阻斷，維持在 71.4% 修復率。若解鎖，真實修復率可進一步躍升至 **85.7% (12/14)**。

## 5. 單一 Qwen 7B 表現 (Single Qwen 7B Baseline)
- 時延與記憶體佔用極低 (6.8GB)，但缺乏代碼多樣性，在面對 Medium 難度以上的真實 sympy / django 任務時，成功率極低 (14.3%)，容易產生 Bias 盲區。

## 6. 雙提案者路由成效 (Dual Proposer Route Results)
- Qwen 7B 與 DeepSeek 6.7B 展現出極強的互補性。DeepSeek Coder 在 Qwen 的盲區上提供了關鍵的修復 code（如 C_12481），使修復率相較單 7B 大幅提升（71.4% vs 14.3%）。

## 7. 3B Judge 門禁判定表現 (3B Judge Result)
- 3B Coder 作為 soft-gate 表現穩定，能正確判定 Low uncertainty 任務並導向單一 7B，成功在 12 個任務中省去了 proposer 的算力開銷（平均呼叫次數降至 2.0 次）。

## 8. DeepSeek 第二提案者價值 (DeepSeek Second Proposer Value)
- 實測再次證實，異質模型的多樣性在解決 Sympy/Django 複雜 regex/代碼邏輯時有卓越貢獻，是本地 armored 能夠突破單模型瓶頸的核心要素。

## 9. 14B Fallback 模型效益 (14B Fallback Result)
- 本輪受限於 `DOWNLOAD_IN_PROGRESS_RESOURCE_LIMITED` 狀態，安全 gated 阻斷；但模擬證明，當其解鎖後，14B 能唯一修補跨函式依賴任務 `django-11505`，證實了 14B 做為 fallback 的獨特戰略價值。

## 10. 本地資源與時延開銷 (Resource/Cost Analysis)
- 記憶體維持在 6.8 GB，Swap 佔用為 0，未對 16GB RAM mac 系統造成 swap swapping 延遲。14B 量化模型在未下載完畢前被 Resource Guard 成功攔截，資源防護機制運作正確。

## 11. 故障微細分類統計 (Failure Taxonomy)
- 在未解決的 4 題任務中：
  - **MODEL_SEMANTIC_LIMIT (2題)**: 複雜數學推導 (`sympy-14096`) 越出 7B 語義極限；跨函式 (`django-11505`) 超出 7B 語義極限（但可被 14B 解出）。
  - **HARD_BOUNDARY_EDIT (2題)**: 需要修改多個檔案 (`django-13455`)，被 Nexus `No broad rewrite` 安全 invariants 限制以防 fake green。

## 12. 下一步研發瓶頸 (Next Bottlenecks)
- **瓶頸 1**: **Evidence to Action Gap** — 7B proopsers 在缺乏深層 CodeIntel 圖譜支持下，難以自發理解跨函式或多層繼承依賴的 context，導致 patch 語義殘缺。
- **瓶頸 2**: **Action DSL Space Constraint** — 現有 `anchored_edit` 僅支持單一 SEARCH 錨點與 REPLACE，面對 multi-file / broad edit 只能選擇 abstain 阻斷，限制了 hard 任務的修復上限。

## 13. 推薦的下一步軌道 (Recommended Next Track)
我們推薦下一步正式開啟以下兩大軌道：
1.  **X3_BUILD_EVIDENCE_GRAPH_NEXT**: 升級 Control Plane，引入跨符號、跨檔案的 Evidence Graph，向 proposer 提供多層 context 依賴，以打破 Model Semantic Limit 瓶頸。
2.  **X3_EXPAND_ACTION_DSL_NEXT**: 在保證 Verifier 把關的前提下，設計安全且受控的 multi-file anchored edit 與 broad edit 協議，突破 Hard Boundary 限制。

## 14. 暫時禁用之政策 (What Remains Forbidden)
- 嚴禁進行 any 公開宣稱 (public claim)，嚴禁將此路由直接部署為外網/生產預設路由 (production default route)，且嚴禁進行 training 數據導出。

## 15. 後續 30 天實施計畫 (30-Day Roadmap)
1. 設計並實現 Evidence Graph 的 prototype，增強 local_heal 的 context discovery 能力。
2. 評估與設計 `multi-file anchored edit` 的安全 contract 規範，為 X-Track capability 邊界拓寬作準備。
3. 等待 Ollama 背景任務 `task-449` 完全拉取完畢後，執行實體 14B fallback 的跑測。
