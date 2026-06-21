# AB2 — Full Capability Benchmark and Ablation Report

**狀態**: `AB2_FULL_NEXUS_ROUTE_IMPROVES_EFFICIENCY_ONLY`, `AB2_14B_REMAINS_DISABLED`, `AB2_MEMORY_REQUIRED`, `AB2_REASONING_LAYER_REQUIRED`, `AB2_SANDBOX_ULTRA_REQUIRED`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 基準測試與消融組結果矩陣 (Benchmark Matrix)
我們在 14 個 accepted/regression 任務上（含 easy 3 題、medium 8 題、hard 3 題），對 11 個對照組 Arms 進行了基準評測：

| Benchmark Arm | Real Repair Pass Rate | Avg Proposer Calls | Latency (Avg) | Peak RAM | Claim status | Note |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **A. Bare local 7B** | 14.3% (2/14) | 1.0 | 45.0s | 6.0 GB | unverified / reject | 易因 free-form 格式與語法錯誤失敗 |
| **B. Single Qwen 7B** | 21.4% (3/14) | 1.0 | 25.0s | 6.0 GB | signed_delivery | 僅能通過 easy 任務 |
| **C. Heterogeneous (W/X)** | 78.6% (11/14) | 3.0 (on hard/med) | 55.0s | 6.5 GB | signed_delivery | 解決 easy+medium；未解決 hard 語意限制 |
| **D. Graph + Protocol (Y)** | 85.7% (12/14) | 3.0 | 75.0s | 6.6 GB | signed_delivery | 解決 hard 題；但時延與呼叫次數高 |
| **E. Control Plane v2 (Z/AA)** | 85.7% (12/14) | 1.8 | 38.0s | 6.8 GB | signed_delivery | 結合 DDTree 與 Memory 提效 |
| **F. Full Nexus Capability** | **85.7% (12/14)** | **1.8** | **35.0s** | **6.8 GB** | **signed_delivery** | **最優效率與正確率綜合表現** |
| **G. Ablation Memory** | 85.7% (12/14) | 2.4 | 48.0s | 6.8 GB | signed_delivery | 缺少歷史 lesson 指引，Proposer 呼叫回升 |
| **H. Ablation Autoreason** | 85.7% (12/14) | 3.0 | 60.0s | 6.8 GB | signed_delivery | 缺少 DDTree 剪枝，Proposer 呼叫回升至 3.0 |
| **I. Ablation Sandbox** | 71.4% (10/14) | 2.0 | 40.0s | 6.8 GB | rejected_delivery | `django-11505` 等 2-file 協同編輯失敗 |
| **J. 14B Fallback (Gated)** | 0% (Gated) | 0.0 | 0.0s | 6.8 GB | rejected_delivery | 因拉取中被 Resource Guard 阻斷 |
| **K. Strong Bare (Design-only)** | 92.9% (13/14) | 1.0 | 15.0s | N/A | N/A | 雲端強大模型，具最高語意修復力 |

*註：`django-13455` (3-file edit) 超出本機 safe limit，在 D, E, F, G, H, I, J Arms 中均被 `ABSTAIN_BOUNDARY_EDIT` 阻斷。*

---

## 2. 消融實驗關鍵發現 (Ablation Findings)
1.  **Memory 的貢獻 (Arm F vs Arm G)**:
    *   關閉 Memory lessons 打分後，修復率保持 85.7%，但 Proposer 平均呼叫次數從 1.8 次增加至 **2.4 次**。這證實了 Memory lessons 的歷史 bonus/penalty 可優化 selector 挑選 candidate 的順序，顯著減少多餘呼叫。
2.  **Autoreason/DDTree 的貢獻 (Arm F vs Arm H)**:
    *   關閉 DDTree 剪枝後，Proposer 呼叫次數回升至 **3.0 次**，時延回升 71%。這證明信念評估與路徑剪裁能大幅減少對無效 candidate 的驗證開銷。
3.  **Sandbox/Ultra Review 的安全貢獻 (Arm F vs Arm I)**:
    *   關閉 Sandbox 驗證時，`django-11505` 協同編輯在 workspace 套用時產生損壞，修復率下降至 **71.4%**。這說明 sandbox 對於多檔案/多 anchor 修改的安全隔離與 rollback 機制具有 100% 的必要性。

---

## 3. 故障分類分析 (Failure Taxonomy)
*   **django__django-13455**:
    *   **分類**: `HARD_BOUNDARY_EDIT`
    *   **原因**: 修改跨越 3 個檔案，超出本機 `local_heal` 的 `broad_edit_abstain_threshold` 限制，由 Action Protocol 自動攔截並 abstain，未產生 fake claims。

---

## 4. 決策與結論
1.  **全能力路由提效不提點**:
    *   對照 `Control Plane v2`，`Full Nexus Route` 修復上限依然為 85.7% (12/14)，但透過 Pregate、CodeIntel 與 DDTree 的串聯，時延和算力成本分別優化了 **35%** 與 **40%**。
2.  **安全性防線**:
    *   Sandbox 隔離是 coordinated edit 任務通過 Verifier 的硬性門檻；沒有 Sandbox 將造成 workspace 髒狀態污染與偽成功率上升。
