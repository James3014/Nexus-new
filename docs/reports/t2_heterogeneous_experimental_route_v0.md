# T2 — Controlled Internal Route Integration

**狀態**: `T2_EXPERIMENTAL_ROUTE_READY_INTERNAL_ONLY`, `T2_3B_JUDGE_ADVISORY_ONLY`  
**整合日期**: 2026-06-21  
**受控路由名稱**: `local_heterogeneous_portfolio_experimental_v0`

---

## 1. 受控手動啟用機制與隔離

為了確保產品線（default path）的安全，本路由被設計為**完全隔離之手動啟用路由**：
*   **手動調用**: 可透過 CLI 命令 `--route local_heterogeneous_portfolio_experimental_v0` 或是環境變數 `NEXUS_ROUTE_OVERRIDE` 進行手動激活。
*   **不影響 Default 路由**: 在預設修復流程中，此異質組合路由仍保持靜默，不進行任何干預。
*   **完整收據鏈 (Receipt Chain)**: 路由在各個階段 (Judge, Proposers, Selection, Verifier) 均會落盤完整的 JSON 收據與 Rationale 紀錄。

---

## 2. 路由決策政策實體化

*   **3B 裁判政策 (`judge_policy.json`)**:
    - **決策**: 判定為 `T2_3B_JUDGE_ADVISORY_ONLY` (僅為諮詢性軟路由門禁)。
    - **理由**: 為了避免小參數模型 (3B) 因對複雜 issue 的片面理解，發生 false-negative 誤擋本可被 proposer 修復的案例。
*   **提案與選擇政策 (`selector_policy.json` 與 `proposer_policy.json`)**:
    - 配置 `qwen2.5-coder:7b-instruct` (Primary) 與 `deepseek-coder:6.7b-instruct` (Second) 獨立提案。當衝突發生時，優先級以 `applier_dry_run_success` (補丁 dry-run 通過) 作為首要的確定性篩選指標。
*   **資源與容量把關 (`resource_guard_policy.json`)**:
    - 持續對 `qwen2.5-coder:14b-instruct` 進行 RAM 動態把關，且完全阻斷 `qwen3-coder-moe` 的加載。
