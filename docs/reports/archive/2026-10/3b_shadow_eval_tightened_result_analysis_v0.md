# 3B Shadow Eval Tightened Result Analysis v0

## 1. Executive Summary

本報告針對 **3B Shadow Eval Tightened Rerun** 的 12 筆模型輸出進行深度品質與工程實用度分析。
* **主要結論**：在收緊 schema 限制後，`qwen2.5:3b` 模型展現了出色的 JSON 合規性與防拒答迴歸。
* **工程實用 verdict**：`useful_as_shadow_signal`（本階段 3B 學生模型具備作為內部低權限 shadow advisory 的實用價值）。
* **核心限制**：此分析為 shadow-only 成果，絕不影響 runtime，且禁止對外宣稱任何 solve-rate。

## 2. Task-Type Utility Analysis

按任務類別（slice_score, failure_class, abstention 各 4 筆）的細部統計如下：

1. **`slice_score`** (4 筆):
   - **合規性**：4/4 筆 parse valid，無 Refusal，無越權。
   - **訊號品質**：3 筆 substantive signal, 1 筆 shallow but valid。
   - **Advisory verdict**：`useful_as_shadow_signal`。理由為模型能將正向解決狀態對齊 score 3，並於 `reason` 中說明依據。
2. **`failure_class`** (4 筆):
   - **合規性**：4/4 筆 parse valid，0% Refusal。
   - **訊號品質**：3 筆 substantive, 1 筆 shallow。
   - **Advisory verdict**：`useful_as_shadow_signal`。模型正確將無錯誤之 row 標記為 `none`，並把 `rejected_semantic_wrong` 正確對應為 `semantic_mismatch`。
3. **`abstention`** (4 筆):
   - **合規性**：4/4 筆 parse valid。
   - **訊號品質**：2 筆 substantive (安全退避), 2 筆 shallow (proceed_shadow_only)。
   - **Advisory verdict**：`useful_as_shadow_signal`。模型在資訊不全或錯誤時，能以 `low` 信心發起 `abstain` 退避，決策模式安全保守。

## 3. Signal Density Analysis

* **High Signal (8 筆)**：
  - `b998eeca08e18f87` / `e42e467d3dcc8805` / `d78615471741966e` / `4085ec30ab09b6b5` / `109346a5fbe4a8ca` / `4bf02ddd630e2020` / `079fd61319ad750d` / `e0d8a3e8b782c7ce`
  - 這些 row 在 `reason` 中明確指出了對應的 metadata（例如 positive verified solve 或是 rejected_semantic_wrong），且正確與評分/分類對應。
* **Medium Signal (4 筆)**：
  - `d7e35cc637fd6c24` / `3fb6cd5f92e8c877` / `d76410255281b7ca` / `d5b5e398a3d4e04e`
  - 理由正確且符合 schema，但未填入 `evidence_fields_used`，內容稍微模板化。
* **Low Signal / Unusable / Schema Only (0 筆)**。

## 4. Confidence Calibration Analysis

* **分佈情況**：Low (2 筆), Medium (9 筆), High (1 筆)。
* **置信度對齊**：
  - 當遇到明確錯誤分類為 `semantic_mismatch` 時，模型以 High 信心預測。
  - 當為正常 solve 但 metadata 資訊有限時，以 Medium 信心預測。
  - 當執行 abstention 退避決策時，正確以 Low 信心預測，展現高度校準的保守防護特質。

## 5. Evidence-Field Usage Analysis

* **欄位引用**：正確使用了 `["type", "status", "count_ops", "positive_verified_solve", "task", "failure_summary", "strategy_context"]` 等資訊，並無捏造任何不存在的欄位。
* **實用判定**：符合 shadow advisory 內部參考所需。

## 6. Task Role Recommendation

我們為 3B 模型推薦以下受限內部角色：
* **Allowed Roles (允許)**：
  1. `slice_score_shadow_advisor` (內部 shadow 評分)
  2. `failure_class_shadow_classifier` (內部 shadow 錯誤分類)
  3. `abstention_shadow_guard` (遇到不確定性時進行退避)
  4. `sample_review_candidate_generator` (產生 review 候選集)
* **Forbidden Roles (嚴格禁止)**：
  - `patch_author` / `route_decider` / `verifier_override` / `runtime_adopt` / `training_export_source` / `public_claim_evidence` (禁止任何修補與對外宣宣稱角色)

## 7. Comparison with Previous Failure Mode

* **Prior Run (第一輪)**：3B 模型為 100% 拒答（apologetic block 拒答格式），造成資訊空洞。
* **Tightened Rerun (本輪)**：拒答率降為 **0%**，且全數解析成功。
* **改善原因**：Schema tightening 嚴格控制了輸出欄位長度、排除 ```json markdown 包裝、並強制 low confidence 退避，這為小模型的生成邊界提供了精準導引。

## 8. Future Decision Matrix

* **推薦下一步**：**3b_shadow_eval_tightened_sample_review_v0** (作為最保守路徑)。
* **待決狀態**：7B 評估與 policy 整合規劃暫時 blocked，直至 owner 審閱此分析報告。

## 9. Governance and Claim Boundary

本階段無額外 model call、無 verifier rerun、無 code patch 修改。
完全符合冷治理冷隔離原則。
