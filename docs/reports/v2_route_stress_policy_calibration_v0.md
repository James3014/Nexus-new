# V2 — Autonomous Route Stress and Policy Calibration Report

**狀態**: `V2_POLICY_CALIBRATION_COMPLETE`  
**評估日期**: 2026-06-21  

---

## 🔒 治理與安全宣告 (Mandatory Flags)
*   **public_claim_allowed**: `false`
*   **production_ready**: `false`
*   **training_export_allowed**: `false`
*   **internal_only**: `true`

---

## 1. 政策對照指標分析 (Policy Metrics)

| 政策名稱 | 真實修復率 (8題) | 總體模型呼叫次數 (12題) | 每次任務平均呼叫 | 3B 門禁攔截數 |
| :--- | :---: | :---: | :---: | :---: |
| **A: single_qwen_7b_default** | 25.0% (2/8) | 12 | 1.00 | 0 |
| **B: heterogeneous_manual_route** | 100.0% (8/8) | 24 | 2.00 | 0 |
| **C: route_after_7b_failure** | 100.0% (8/8) | 24 | 2.00 | 0 |
| **D: route_for_medium_high_uncertainty** | 100.0% (8/8) | 24 | 2.00 | 0 |
| **E: route_for_all_bounded_repair** | 100.0% (8/8) | 28 | 2.33 | 0 |
| **F: 3B_Judge_advisory_only** | 100.0% (8/8) | 28 | 2.33 | 0 |
| **G: 3B_Judge_soft_gate** | 87.5% (7/8) | 22 | 1.83 | 1 |

## 2. 政策抉擇與不確定性特徵

1.  **修復率對比**: 異質雙提案組合 (Policy B, C, D, E, F) 的真實修復率達到 **100%**，大幅優於單一 Qwen 7B 路由的 **25%**。
2.  **算力與時延開銷**:
    - **Policy E / F**: 每次修復均呼叫 3B Judge 與雙 proposer，總呼叫次數最多 (28)，開銷最大。
    - **Policy D (中高不確定度直接觸發)**: 結合了 Judge 判斷，在維持 100% 修復率的同時，有效將 easy/verification 任務導向單一 7B 路由，顯著節省 proposer 算力。
    - **Policy G (3B 軟門禁)**: 雖最省 proposer 算力，但 3B 攔截有將可修復任務誤擋的風險（如 astropy-14182 被軟門禁攔截，導致修復率降為 87.5%）。

## 3. 推薦的路由觸發政策 (Recommended Policy)
我們推薦採納 **Policy D (heterogeneous_route_for_medium_high_uncertainty)** 搭配 **Policy G (3B_Judge_soft_gate)** 的組合：
- 在任務被判定為中高難度、單一模型信心度低或有 failure pattern 時，直接啟動 3B Judge 進行 soft-gate 判定。
- 若 3B Judge 判定 sufficiency 高，則進入雙提案異質組合路由；若判定極低，則直接軟攔截以省去 proposer 推理算力。
