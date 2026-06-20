# Local 7B/14B Repair Final Expansion Rollup v0

## 1. Executive Summary
本報告正式記錄 Local 7B/14B 修復與擴充能力整個實驗鏈（4-task expansion, deferred concurrency, abstention-only）的終期彙整（Rollup）。

## 2. Mainline Calibration
本次實驗鏈的彙整結果，成功驗證了 Local 7B/14B 模型在受控測試沙盒中對於確定性、並發以及棄權保護這三大主線能力的進步。該成果提供了一套安全、可追溯的模型修復驗證標準，為後續的對齊和治理奠定了客觀的數據與流程依據。

## 3. Scope
本次 Rollup 包含以下三個子批次：
1. **4-task expansion batch**：CLOSED_WITH_WARNING
2. **deferred concurrency batch**：CLOSED_WITH_WARNING (包含 `concurrency_bug_03`)
3. **abstention-only batch**：CLOSED (包含 `sympy_matrices_abstention_candidate`)

## 4. Final Outcome Counts
* **總任務結果 (total_task_outcomes)**：6
* **環境預先驗證數 (workspace_pre_verified_count)**：1 (即 `astropy_14526`)
* **模型修復嘗試數 (model_repair_attempt_count)**：4
* **模型修復成功數 (model_repair_success_count)**：4
* **棄權控制成功數 (abstention_control_success_count)**：1 (即 `sympy_matrices_abstention_candidate`)
* **驗證器最終通過數 (final_verifier_pass_count)**：5
* **帶警告封閉批次數 (closed_with_warning_count)**：2
* **乾淨封閉批次數 (closed_clean_count)**：1

## 5. Task Outcome Table
| 任務識別碼 (Task ID) | 分類 (Category) | 最終狀態 | 修復成功 | 控制成功 | 證據層級 | 備註 |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| `astropy_14526` | workspace_pre_verified | verifier_passed | false | false | subprocess_python_task_venv_verified | 驗證器就緒，非模型修復 |
| `sympy_polys_01` | model_repair_success | verifier_passed | true | false | subprocess_pytest_nexus_venv_verified | 模型成功生成 patch 並通過 |
| `nexus_verifier_http_01` | model_repair_success | verifier_passed | true | false | subprocess_pytest_nexus_venv_verified | verifier 範圍包含既存測試，無 code 變更 |
| `nexus_protocol_boundary_01` | model_repair_success | verifier_passed | true | false | subprocess_pytest_nexus_venv_verified | ENV_BLOCKED 遙測語意驗證成功 |
| `concurrency_bug_03` | model_repair_success_with_warning | verifier_passed | true | false | subprocess_pytest_nexus_venv_verified | 併發 flakiness 風險高，repeatability 較淺 |
| `sympy_matrices_abstention_candidate` | abstention_control_success | abstained | false | true | abstention_correct | 原始碼目錄缺失，正確進行政策棄權 |

## 6. Evidence Tiers
* `subprocess_python_task_venv_verified`: 1
* `subprocess_pytest_nexus_venv_verified`: 4
* `abstention_correct`: 1
* `verifier_not_run_valid`: 1
* `repeatability_passed`: 1 (針對 concurrency_bug_03)

## 7. Capability Interpretation
### 允許之內部宣稱 (Allowed Internal Interpretation)
* Local 7B/14B 控制修復沙盒成功完成了 4 個由模型產生的修復任務。
* 完成了 1 個環境預先驗證任務，用以驗證驗證器的可用性，但這不屬於模型修復成功。
* 完成了 1 個棄權候選任務，證明模型在源錨點缺失下具備正確棄權的控制自律（control_success=true，repair_success=false）。
* 所有的執行都在沙盒邊界內合規完成，支援內部能力進展的判定。

### 禁用之宣稱 (Forbidden Interpretation)
* 禁用宣稱任何 GPT/Gemini 對等性能、基準測試了解、生產環境就緒、自主修復部署、Runtime 或 Routing 整合。
* 禁用將棄權正確判定宣稱為「修復成功」，亦不具備訓練資料導出或 S2T 導出之合規資格。

## 8. Residual Risks
* `astropy_14526` 的環境預先驗證存在歸因風險。
* `nexus_verifier_http_01` 的 verifier 範圍包含了既存測試。
* `concurrency_bug_03` 具有高併發 flakiness 風險，且重複性驗證次數僅有 1。
* 棄權任務的 `sympy/matrices/` 原始碼缺失依然未解決。
* 無任何公開宣稱與訓練導出合規。
* 未與 StraTA S1 進行連接。

## 9. Governance
本 Rollup 完全符合治理邊界：
* `runtime_integration`: false
* `routing_integration`: false
* `verifier_override`: false
* `training_export`: false
* `public_claim`: false
* `automatic_adoption`: false
* `s2t_export`: false
* `benchmark_claim`: false
* `gpt_gemini_parity_claim`: false
* `production_ready`: false
* `owner_decision_required_for_next_task`: true

## 10. Owner Decision Options
後續行動需要 Owner 決策，可用選項包括：
* `PAUSE_AND_ARCHIVE_LOCAL_7B_14B_REPAIR_EXPANSION` — **推薦決策**。當前擴充已產生有用的內部數據。在進行下一步新實驗之前，建議將當前已完成的證據鏈進行歸檔。
* `APPROVE_STRATA_S1_ALIGNMENT_REVIEW` (核准 S1 連線審查)
* `APPROVE_CONCURRENCY_REPEATABILITY_HARDENING` (核准併發重複性強化)
* `APPROVE_S2T_EXPORT_ELIGIBILITY_REVIEW` (核准 S2T 資料導出審查)
* `APPROVE_NEXT_EXPANSION_APPROVAL_PACKET` (核准新一輪擴充包)
