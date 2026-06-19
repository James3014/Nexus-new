# 3B Shadow Advisory Stage 3 Human Review Annotation Plan v0

## 1. Executive Summary (執行摘要)
本報告記錄 **3B Shadow Advisory Stage 3 Human Review Annotation Plan v0** (影子諮詢第三階段人類審查註釋規劃) 的設計規格。本任務為純規劃/設計任務 (Plan-only / Design-only)，旨在為第二階段已封存的 36 筆影子諮詢推理收據 (Receipts) 定義一套「人類審查輔助註釋」之渲染與審核協定。本階段絕無模型呼叫、無運行時連接，亦無任何代碼修補或公開宣稱，全部規劃皆在冷治理防線內進行。

* **規劃狀態**：`plan_status: READY_FOR_REVIEW`
* **基準 Commit Hash**：`d2b415c4`
* **輸入數據來源**：`artifacts/runtime/3b_shadow_advisory_stage2_expansion_execution_v0/shadow_advisory_receipts.jsonl` (共 36 筆)
* **註釋權限級別**：`authority_level: non_authoritative` (非決策性、非權威性)
* **人類審查必要性**：`reviewer_must_confirm: true` (必須經人類審查者二次確認)

## 2. Annotation Objectives (註釋目標)
* **允許的目標 (Allowed)**：
  1. 幫助審查者注意到候選風險 (`help reviewer notice candidate risk`)。
  2. 彙總 advisory 訊號 (`summarize advisory signal`)。
  3. 揭露 confidence 與 evidence 欄位 (`expose confidence and evidence fields`)。
  4. 顯示不確定性來源 (`show uncertainty source`)。
  5. 標記需要人類注意的 rows (`flag rows needing human attention`)。
  6. 為離線審查提供中等權重 context (`provide medium-weight context for offline review`)。
* **禁止的目標 (Forbidden)**：
  1. 決定任務路由 (`decide task route`)。
  2. 核准或拒絕 patch (`approve/reject patch`)。
  3. 覆蓋驗證器之結果 (`override verifier`)。
  4. 標記問題解決 (`mark solve`)。
  5. 設定訓練資料導出資格 (`set training eligibility`)。
  6. 支持公開基準測試宣稱 (`support public claim`)。
  7. 改變運行時行為 (`change runtime behavior`)。

## 3. Annotation Surfaces (註釋介面)
* **允許的介面 (Allowed)**：
  - 人類審查隊列註釋 (`human_review_queue_annotation`)
  - 離線報告側邊欄 (`offline_report_sidebar`)
  - 分流摘要卡片 (`triage_summary_card`)
  - 證據欄位高亮 (`evidence_field_highlight`)
  - 不確定性備註 (`uncertainty_note`)
  - 審查者清單預填 (`reviewer_checklist_prefill`)
  - 審計分類帳參考 (`audit_ledger_reference`)
* **禁止的介面 (Forbidden)**：
  - 運行時路由器 (`runtime_router`)
  - 修補程式輸入 (`patcher_input`)
  - 驗證器決策 (`verifier_decision`)
  - 晉級門禁 (`promotion_gate`)
  - 訓練導出門禁 (`training_export_gate`)
  - 公開基準測試報告 (`public_benchmark_report`)
  - 自動接受或拒絕 (`automated_acceptance_or_rejection`)

## 4. Human Review Annotation Schema (審查註釋 Schema)
所有為這 36 筆數據生成的註釋必須符合以下 Schema：
* **必填欄位 (Required)**：
  - `annotation_id`, `source_row_id`, `receipt_id`, `task_type`, `advisory_role`, `advisory_signal_summary`, `confidence`, `signal_weight`, `evidence_fields_used`, `uncertainty_source`, `reviewer_action_hint`
* **常量限制欄位 (Constants)**：
  - `reviewer_must_confirm`: `true` (必須經人類審查者確認)
  - `authority_level`: `"non_authoritative"` (非權威性)
  - `runtime_effect`: `false` (不影響運行時)
  - `routing_effect`: `false` (不影響路由)
  - `verifier_effect`: `false` (不影響驗證器)
  - `training_export_allowed`: `false` (禁止導出用於訓練)
  - `public_claim_allowed`: `false` (禁止公開宣稱)

## 5. Annotation Rendering Rules (渲染規則)
* **必須顯示 (Must Show)**：
  - `"3B shadow advisory — non-authoritative"` (明確標註為非權威的影子諮詢)
  - `confidence` (模型信心度)
  - `evidence_fields_used` (所採用的證據欄位)
  - `uncertainty_source` (若有不確定性來源必須顯示)
  - `reviewer_must_confirm` (提示審查者必須確認)
  - `policy_gate_status` (政策門禁狀態)
* **禁止顯示為 (Must NOT Show As)**：
  - 最終決策 (`final_decision`)
  - 路由指令 (`routing_instruction`)
  - 修補指令 (`patch_instruction`)
  - 驗證結果 (`verifier_result`)
  - 訓練信號 (`training_signal`)
  - 公開宣稱 (`public_claim`)
* **轉換限制**：禁止將 advisory 轉換為任何形式的自動化指令。

## 6. Reviewer Checklist Schema (審查者清單)
審查介面應預填並要求人類審查者勾選確認以下項目：
1. 影子諮詢訊號是否與該任務具體相關？ (`is_advisory_signal_relevant`)
2. 所使用的證據欄位是否具有實質意義？ (`are_evidence_fields_meaningful`)
3. 模型信心度是否已合理校準？ (`is_confidence_calibrated`)
4. 不確定性來源是否已被明確指出？ (`is_uncertainty_explicit`)
5. 是否無任何權限溢出 (Authority Creep)？ (`is_authority_creep_absent`)
6. 審查者採取的決策：忽略、考慮或升級？ (`reviewer_action_ignore_consider_or_escalate`)
7. 離線確認是否已完成？ (`offline_only_confirmed`)

## 7. Fail-Closed Annotation Gate (阻斷門禁)
若檢測到以下任何一項異常，必須自動 Fail-Closed 阻斷該行註釋：
* 缺失推理收據 (receipt)。
* 政策門禁未通過。
* `runtime_effect` 屬性為 `true`。
* `adoption_allowed` 屬性為 `true`。
* 檢測到 `routing_effect` 或 `verifier_effect`。
* 檢測到修補建議。
* `training_export_allowed` 或 `public_claim_allowed` 為 `true`。
* 證據欄位為空。
* 缺失 confidence 欄位。
* `reviewer_must_confirm` 被設為 `false`。

## 8. Artifact-Only Replay Plan (重放計劃)
* **實體化目標**：`3b_shadow_advisory_stage3_annotation_materialization_v0`
* **輸入收據**：`artifacts/runtime/3b_shadow_advisory_stage2_expansion_execution_v0/shadow_advisory_receipts.jsonl`
* **預期規模**：36 筆。
* **執行邊界限制**：
  - `model_calls_allowed`: `false` (禁止呼叫模型)
  - `runtime_connection_allowed`: `false` (禁止運行時連接)
  - `routing_integration_allowed`: `false` (禁止路由整合)
  - `verifier_integration_allowed`: `false` (禁止驗證器整合)
  - `training_export_allowed`: `false` (禁止訓練導出)
  - `public_claim_allowed`: `false` (禁止公開宣稱)
  - `requires_plan_review_first`: `true` (必須先通過計畫審查)

## 9. Blocked Decisions (阻斷決策)
以下決策保持 **Blocked** 狀態：
- 運行時採用 (`runtime_adoption`)
- 路由整合 (`routing_integration`)
- 覆蓋驗證器 (`verifier_override`)
- 修補權限 (`patch_authority`)
- 訓練導出 (`training_export`)
- 公開宣稱 (`public_claim`)
- 無 Owner 核准的 7B/14B 影子執行 (`7b_shadow_eval_execution_without_owner_approval` 等)
- 自動接受或拒絕決策 (`automatic_decision`)

## 10. Governance Summary (治理合規總結)
本規劃案完全符合冷治理合規條款：
* 額外模型呼叫：`false`
* 評估重跑：`false`
* 驗證器重跑：`false`
* `M6` 執行：`false`
* 來源獲取：`false`
* 原始碼修改：`false`
* 運行時連接：`false`
* 訓練導出與公開宣稱：`false`

## 11. Recommended Next Step (推薦下一步)
* **下一步**：`3b_shadow_advisory_stage3_annotation_plan_review_v0`
* **說明**：對本規劃所定義之渲染、阻斷與審查清單規則進行人類/規則式審核，確保安全邊界無虞。
