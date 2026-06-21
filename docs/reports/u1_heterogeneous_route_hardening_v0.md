# U1 — Route Hardening and Receipts

**狀態**: `U1_ROUTE_HARDENED_INTERNAL_MANUAL`, `U1_SELECTOR_HARDENED`, `U1_3B_JUDGE_SOFT_GATE_ONLY`  
**加固日期**: 2026-06-21  
**受控路由名稱**: `local_heterogeneous_portfolio_experimental_v0`

---

## 1. 路由調用與收據架構加固

為了使實驗路由具備完備的審計追蹤能力，我們完成了以下加固工作：
*   **顯式調用警告 (`route_invocation_contract.json`)**:
    - 設定當使用 `--route local_heterogeneous_portfolio_experimental_v0` 時，強制於控制台輸出 `⚠️ [INTERNAL WARNING] Running controlled experimental route. Not for production routing.`，加強防護意識。
*   **收據合規性檢驗 (`receipt_schema.json`)**:
    - 定義了 21 個強制收據欄位，包括 `source_hash`、`candidate_count`、`selected_candidate_source` 與 `final_status`。
    - 內置強制性安全 flags 結構，嚴格限制 `public_claim_allowed=false` 且 `internal_only=true`。

---

## 2. 篩選評分與門禁政策加固

*   **篩選政策硬化 (`selector_policy.json`)**:
    - 設計了權重評分：機制匹配 (30)、applier dry-run 成功 (50)、proposer 多樣性 bonus (20) 等。
    - **硬性拒絕規則**: 任何包含 Prose  contamination、invalid JSON、缺失 `evidence_id`、缺失 `source_hash` 或是跨多檔案修改的 candidate，均會被選擇器直接拒絕 (Hard Reject)。
*   **3B 評判門禁政策 (`judge_gate_policy.json`)**:
    - 配置為 `U1_3B_JUDGE_SOFT_GATE_ONLY`。僅在 `evidence_sufficiency=low` 且有明確 Context 遺失風險時才硬性阻斷，其餘情況作為 Soft Gate (Advisory) 運作，並即時收集 `false_abstain_rate` 指標。
