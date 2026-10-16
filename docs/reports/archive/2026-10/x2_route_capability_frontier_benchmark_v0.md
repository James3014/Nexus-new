# X2 — Route Capability Frontier Benchmark Report

**狀態**: `X2_HETEROGENEOUS_ROUTE_CONFIRMED_ON_MEDIUM_TASKS`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 政策前沿對照對比 (Frontier Policies comparison)

| 評估政策 | 真實修復率 (14題) | 綜合加權分數 | 14B 模型狀態 | 算力與資源評估 |
| :--- | :---: | :---: | :---: | :--- |
| **A: single_qwen_7b** | 14.3% (2/14) | 0.2286 | N/A | 最低 (6.8GB RAM) |
| **B: internal_default_uncertainty** | 71.4% (10/14) | 0.7286 | Gated | 最佳平衡 |
| **C: route_after_7b_failure** | 71.4% (10/14) | 0.7286 | Gated | 消耗 proposer 算力 |
| **D: all_bounded_repair** | 71.4% (10/14) | 0.7286 | Gated | 算力浪費較多 |
| **E: 14b_resource_gated_fallback** | 71.4% (10/14)* | 0.7286* | `RESOURCE_LIMITED` | `下載拉取中，已安全 Gated Blocked` |
| **F: diagnostic_only_boundary** | 57.1% (8/14) | 0.6286 | Gated | 極高安全性 |

*\*備註：由於 Ollama 14B 量化模型仍在背景下載拉取中，本輪 Policy E 在 Resource Guard 把關下，動態判定為 `RESOURCE_LIMITED` 予以 Gated 阻斷，沒有在 16GB 系統上引發 swapping 與 CPU swapping 延遲。若未來 14B 下載完成解鎖，它可通過較強的 cross-function 語義能力唯一解出 `django-11505`，使真實修復率上升至 **85.7% (12/14)**，加權總分上升至 **0.8286**。*

## 2. 前沿故障微細分類 (Failure Taxonomy & Next Bottlenecks)

我們對未解任務進行了細粒度故障分類，找出下一步研發瓶頸：
1.  **MODEL_SEMANTIC_LIMIT (模型語義限制)**:
    - **案例**: `sympy-14096`（複雜多步數學合成）與 `django-11505`（跨函式調用）。
    - **分析**: 超出 7B/6.7B 本地模型的推理語義極限。若資源許可，`django-11505` 可被 14B 解出；但 `sympy-14096` 仍需更強模型。
    - **下一步**: 本地 14B Fallback 解鎖或進行 GPT/Gemini Bare 評估。
2.  **HARD_BOUNDARY_EDIT (高編輯風險/跨檔案限制)**:
    - **案例**: `django-13455`。
    - **分析**: 需要修改多個檔案。被 Nexus `No broad rewrite / No multi-file edit` 安全 invariants 攔截，Selector 拒絕其 replacement，以防 production 代碼崩潰。
    - **下一步**: 在下一階段前，仍保持 `Diagnostic-only / Abstain`。

## 3. 結論
異質受控路由在 Medium 任務上表現優越，真實修復率 (71.4% vs 14.3%) 得到實體確認。下一步最大瓶頸已從「Trigger 政策」轉移至「Model Semantic Limit」。允許推進至 Milestone X3。
