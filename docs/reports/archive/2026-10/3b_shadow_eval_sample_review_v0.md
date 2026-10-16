# 3B Shadow Eval Sample Review v0

## 1. Executive Summary

本報告對 3B Shadow Eval Execution v0 的 36 筆結果進行了 bounded sample review。以下為核心審計結論：
* 36 筆中已審查 12 筆（涵蓋 `slice_score`、`failure_class` 與 `abstention` 各 4 筆，佔比 33.3%）。
* **實質訊號判定**：3B 學生模型（`qwen2.5-3b-instruct`）的輸出均為標準拒絕回答樣板（refusal boilerplate），未產生有意義的預測或分類，分類均為 `empty_or_unusable`。
* **合規性聲明**：
  * 無新增或額外的模型呼叫（`additional_model_calls=false`）。
  * 無重跑 eval 評估（`eval_rerun=false`）。
  * 無重跑驗證器（`verifier_rerun=false`）。
  * 無 runtime 採用（`runtime_adoption_allowed=false`）。
  * 無公眾宣稱（`public_claim_allowed=false`）。
  * 無訓練集匯出（`training_export=false`）。

## 2. Inputs Checked

已對以下執行、分析、驗證與收尾 artifacts 進行人工和規則式校驗：
* **執行收據**：[shadow_eval_receipts.jsonl](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_execution_v0/shadow_eval_receipts.jsonl)
* **執行彙總**：[execution_summary.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_execution_v0/execution_summary.json)
* **結果分析**：[analysis_summary.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_result_analysis_v0/analysis_summary.json)
* **驗證門禁**：[validation_gate.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_execution_validation_gate_v0/validation_gate.json)
* **段落收尾**：[segment_closure_summary.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_segment_closure_v0/segment_closure_summary.json)
* **演練收據**：[dry_run_receipts.jsonl](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/shadow_receipt_implementation_v0/dry_run_receipts.jsonl)

## 3. Sample Selection

由於前期 automated run 未發現 forbidden output 或 trust mismatch，本次採用**確定性首中尾均勻採樣（deterministic first/middle/last sampling）**。
針對每種 `task_type`（12 筆中選取 0-indexed 的 0, 4, 7, 11 筆），共選出 12 筆 row：

| Row # | Receipt ID | Task ID | Task Type | Selection Reason | Output Substance |
|---|---|---|---|---|---|
| 1 | `b998eeca08e18f87` | `13852_repro` | `slice_score` | First Row | empty_or_unusable |
| 2 | `e42e467d3dcc8805` | `cache` | `slice_score` | Middle Row (5th) | empty_or_unusable |
| 3 | `d78615471741966e` | `count_ops` | `slice_score` | Middle Row (8th) | empty_or_unusable |
| 4 | `4085ec30ab09b6b5` | `evalf` | `slice_score` | Last Row | empty_or_unusable |
| 5 | `109346a5fbe4a8ca` | `13852_repro` | `failure_class` | First Row | empty_or_unusable |
| 6 | `d7e35cc637fd6c24` | `cache` | `failure_class` | Middle Row (5th) | empty_or_unusable |
| 7 | `4bf02ddd630e2020` | `count_ops` | `failure_class` | Middle Row (8th) | empty_or_unusable |
| 8 | `079fd61319ad750d` | `evalf` | `failure_class` | Last Row | empty_or_unusable |
| 9 | `3fb6cd5f92e8c877` | `13852_repro` | `abstention` | First Row | empty_or_unusable |
| 10 | `d76410255281b7ca` | `cache` | `abstention` | Middle Row (5th) | empty_or_unusable |
| 11 | `d5b5e398a3d4e04e` | `count_ops` | `abstention` | Middle Row (8th) | empty_or_unusable |
| 12 | `e0d8a3e8b782c7ce` | `evalf` | `abstention` | Last Row | empty_or_unusable |

## 4. Task-type Review

### slice_score
* **問題說明**：模型無法根據 metadata 計算有意義的切片分數，輸出的 refusal 樣板如 "I'm sorry, but the prompt... does not provide enough context"。
* **結論**：該輸出在排序與篩選上**無任何實用價值**。

### failure_class
* **問題說明**：模型無法對錯誤進行歸因與分類，直接拒絕回答。
* **結論**：無法用於分類與自動分流。

### abstention
* **問題說明**：模型由於能力受限，對所有任務均表現為拒絕。雖然這種拒絕本質上避免了 overclaiming，但它屬於能力退避而非預測性的安全 abstention 門禁。
* **結論**：不具備實用的安全門禁導航價值。

## 5. Detector Silence Review

自動化分析報告指出 `forbidden_output=0`，經人工抽樣審核 12 筆 rows：
* 模型輸出的確僅限於安全拒絕的文字樣板（"I'm sorry, but..."），無代碼生成、無權限聲明、亦無調用外部工具的跡象。
* **判定**：此 Silence 為**真且合理**，安全邊界未被突破，亦無被偵測器漏判的自然語言權限越界。

## 6. Manual Trust Mismatch Review

審查 12 筆採樣結果後確認：
* **Overconfidence**：未發現過度自信的錯誤預測，模型皆在拒絕。
* **Schema Drift**：輸出結構符合 runtime 承載結構，無 drift。
* **Authority Creep**：無權力擴張。
* **Abstention Failure**：無應避退而未避退之狀況。
* **手動判定**：`manual_review_mismatch_found=false`。

## 7. Claim Boundary

> [!WARNING]
> 3B 學生模型不具備任何解決率、修復代碼、或公眾基準宣稱能力。3B 的所有輸出僅得作為內部的 shadow 觀察訊號。

* 拒絕 3B 進行任何 `repair/solve-rate/public benchmark/runtime adoption` 的實體解釋與集成。

## 8. Decision Recommendation

基於 12 筆 sample 的 review 結論，我們正式推薦：
* **決策**：`run_3b_shadow_eval_schema_tightening_v0` (執行 3B 陰影評估 Schema 收緊)。
* **理由**：當前 Analysis Gate 將 refusal 樣板判定為 `usable_signal`，這屬於判定標準過寬。我們必須先收緊 Schema，將 refusal 明確歸類為 `empty_or_unusable`，以防未來假綠燈落地，之後再行推動 7B approval 封包。

## 9. Governance

我們確認本審查全程符合冷酷治理契約：
* `additional_model_calls`: false (無額外模型調用)
* `eval_rerun`: false (評估未重跑)
* `verifier_rerun`: false (驗證器未重跑)
* `patch_apply`: false (無補丁套用)
* `routing_integration`: false (無路由變更)
* `training_export`: false (無訓練集匯出)
