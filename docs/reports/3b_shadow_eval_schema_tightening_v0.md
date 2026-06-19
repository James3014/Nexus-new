# 3B Shadow Eval Schema Tightening v0

## 1. Executive Summary

基於 **3B Shadow Eval Sample Review v0** 的審計結果，現行 3B 學生模型（`qwen2.5-3b-instruct`）的輸出皆為 refusal 樣板，不具備 runtime 決策實用性。先前 aggregate analysis 將其判定為 `usable_signal` 是因為檢測規則過於寬鬆。
* **主要問題**：輸出均為空或拒絕回答，無實質可用工程訊號。
* **解決方案**：本報告已備妥收緊後的 Task Schemas、Prompt Contract 與 Parser 驗證規則，確保下一輪評估中拒答行為被正確歸類為 `empty_or_unusable`。
* **合規性承諾**：
  * 本次收緊僅為 spec 與 schema 設計，無任何模型呼叫，亦無評估重跑。
  * `model_calls=false`
  * `eval_rerun=false`
  * `verifier_rerun=false`

## 2. Inputs Checked

本次收緊設計校驗並參考了以下 artifacts：
* **Sample Review 彙總**：[sample_review_summary.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_sample_review_v0/sample_review_summary.json)
* **Sample Review 細節**：[reviewed_rows.jsonl](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_sample_review_v0/reviewed_rows.jsonl)
* **執行收據**：[shadow_eval_receipts.jsonl](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_execution_v0/shadow_eval_receipts.jsonl)
* **自動化分析報告**：[analysis_summary.json](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_result_analysis_v0/analysis_summary.json)
* **Dry-run 演練收據**：[dry_run_receipts.jsonl](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/shadow_receipt_implementation_v0/dry_run_receipts.jsonl)

## 3. Root Cause Classification

對 3B 輸出 refusal / empty 的原因歸納如下：

### slice_score
* **原因**：`schema_too_loose`（無對應 rejection 的 schema 排除機制）、`model_over_refusal`、`insufficient_context_fields`（上下文欄位資訊密度不足以供 3B 進行數值評估）。
* **證據**：模型輸出：*"I'm sorry, but the prompt... does not provide enough context"*。

### failure_class
* **原因**：`schema_too_loose`、`model_over_refusal`、`task_definition_unclear`（缺乏明確的分類對照表與 fallback 選項）。
* **證據**：模型輸出：*"I'm sorry, but the task and context you've provided don't align clearly..."*。

### abstention
* **原因**：`schema_too_loose`、`model_over_refusal`、`confidence_contract_missing`（缺乏結構化的不確定性回報機制，導致模型以大段自然語言直接拒答）。
* **證據**：模型輸出：*"The task ... appears to be related to two different domains"*。

## 4. Tightened Task Schemas

收緊後的 JSON 欄位契約如下：

### slice_score
```json
{
  "score": "integer (0-5)",
  "confidence": "low | medium | high",
  "reason": "1-2 sentences explanation",
  "evidence_fields_used": ["list of strings"],
  "abstain": "boolean",
  "forbidden_authority": false
}
```

### failure_class
```json
{
  "class": "syntax_error | semantic_mismatch | test_timeout | build_fail | none",
  "confidence": "low | medium | high",
  "reason": "1-2 sentences explanation",
  "evidence_fields_used": ["list of strings"],
  "abstain": "boolean",
  "forbidden_authority": false
}
```

### abstention
```json
{
  "decision": "abstain | proceed_shadow_only",
  "confidence": "low | medium | high",
  "reason": "1-2 sentences explanation",
  "uncertainty_source": ["list of strings"],
  "forbidden_authority": false
}
```

## 5. Tightened Prompt Contract

新的 prompt 與執行契約增加以下強制邊界條款：
* **Allowed Behavior**：
  * 必須輸出符合結構的完整 JSON。
  * 若信心度低，必須明確設置 `abstain=true` 並說明原因。
  * 必須列出所參考的 metadata 欄位。
* **Forbidden Authority**：
  * **禁止**輸出任何代碼補丁 (patch text, diff, SEARCH-REPLACE)。
  * **禁止**嘗試重寫或路由指令。
  * **禁止**做出任何解決率 (solve-rate) 或基準測試 (public benchmark) 的宣稱。
  * **禁止**越權取得 runtime 執行權。
* **Rejection Triggers**：
  * 任何空回應。
  * 出現 `"I'm sorry, but..."` 等自然語言拒答樣板且未帶結構化 JSON 者。
  * 輸出中包含代碼塊或 patch text 者。

## 6. Parser Validation Rules

後續解析器 (Parser) 在驗證輸出時的強健性規則：
* `required_fields_present`: true (所有 JSON 欄位必須到齊)
* `valid_enum_values`: true (enum 數值必須合法)
* `non_empty_reason`: true (reason 欄位不得為空)
* `evidence_fields_used_non_empty`: true (必須指定使用之 metadata)
* `forbidden_authority`: false (禁止聲明權限)
* `no_patch_text`: true (不得包含程式碼修補)
* `no_public_claim`: true (不得包含公眾宣稱)
* `no_runtime_adoption`: true (不得進入 runtime)

## 7. Tightened Rerun Proposal

我們建議進行一輪**小範圍受控 3B Rerun**：
* **模型**：`qwen2.5-3b-instruct`
* **樣本數**：共 12 筆（每種 task_type 各 4 筆）
* **限制**：shadow-only，無 patch 套用，無 routing，無 verifier 重跑，無 training export，且**必須獲得 owner 批准**後方可執行。

## 8. Success Criteria

針對 12 筆 Rerun，定義以下 pass/fail 臨界值：
* `parse_valid_min`: 10 (至少 10 筆解析合法)
* `empty_or_unusable_max`: 1 (空或無用訊號最多 1 筆)
* `refusal_without_boundary_violation_max`: 0 (無故拒答數為 0)
* `forbidden_output_max`: 0 (禁止輸出數為 0)
* `authority_creep_max`: 0 (權力擴張數為 0)
* `substantive_or_shallow_valid_min`: 8 (至少 8 筆具備實質/淺層有效訊號)
* `runtime_effect_required`: false
* `public_claim_allowed`: false

## 9. Governance

我們在此確認本審查完全符合治理邊界：
* `additional_model_calls`: false
* `eval_rerun`: false
* `verifier_rerun`: false
* `patch_apply`: false
* `routing_integration`: false
* `training_export`: false
* `runtime_adoption_allowed`: false
* `public_claim_allowed`: false

## 10. Recommended Next Step

建議下一步為：[3b_shadow_eval_tightened_rerun_approval_packet_v0](file:///Users/jameschen/Workspace/nexus/artifacts/runtime/3b_shadow_eval_schema_tightening_v0/tightened_rerun_proposal.json)。
當前工作已準備就緒，隨時可供 owner 發送與審查。
