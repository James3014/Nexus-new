# W1 — Uncertainty Trigger Integration Report

**狀態**: `W1_TRIGGER_READY_INTERNAL_ONLY`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 不確定度分流觸發器規則 (Trigger Policy)
我們實作了基於 13 個不確定度特徵的動態觸發政策：
- **Low Uncertainty**: 當 `evidence_confidence` 與 `ranking_gap` 均為 high 且無 prior failure 時，路由鎖定為 `single_qwen_7b_s1_ranked`（如 `astropy-13236` 與 `sympy-13031`）。
- **Medium/High Uncertainty**: 當特徵權重分數得分 >= 2 時，觸發異質雙提案路由 `local_heterogeneous_portfolio_experimental_v0`（如 `C_12481` 與 `C_13453`）。
- **Boundary/High-Risk**: 當預期編輯風險為 high 時，觸發 `diagnostic_only_owner_approval` 路由，禁止自動修復。
- **Resource Blocked Fallback**: 當 resource_guard 動態阻斷（如記憶體不足）時，雙提案路由安全退回至單一 7B 路由，杜絕 swapper 慢速推理。

## 2. Dry Run 分流結果 (Dry Run Trigger Results)

| 任務 ID | 預估不確定度 | 觸發理由 | 最終選定路由 | 資源守衛結果 |
| :--- | :---: | :--- | :--- | :---: |
| **C_12481** | `high` | Low evidence, narrow gap, failure pattern | `local_heterogeneous_portfolio_...` | `PASS` |
| **C_13453** | `medium` | Low evidence, medium ambiguity | `local_heterogeneous_portfolio_...` | `PASS` |
| **astropy-13236** | `low` | High evidence, clear gap | `single_qwen_7b_s1_ranked` | `PASS` |
| **sympy-13031** | `low` | High evidence, clear gap | `single_qwen_7b_s1_ranked` | `PASS` |
| **boundary_edit_test** | `boundary` | High expected edit risk | `diagnostic_only_owner_approval` | `PASS` |
| **resource_blocked_test** | `medium` (fallback) | Resource blocked (RAM full) | `single_qwen_7b_s1_ranked_fallback`| `RESOURCE_BLOCKED` |

## 3. 結論
Uncertainty Trigger 分流判定整合成功。允許推進至 Milestone W2。
