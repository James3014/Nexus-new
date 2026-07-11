# N30R V2 Local Model Armor Regression Recovery Decision Report

## 1. 任務背景與 Regression 根因

在 N30R V2 Paired Evaluation 中，我們先前發現了 **Armor Qwen 7B 出現退化（Regression）** 的現象：
在第四題 `n30r_smoke_multi` 任務中，Bare 版本能正確修復，但穿戴了 Armor 的 Core 版本卻失敗。

經過深入診斷，定位了以下兩個核心 Regression 根因以及 runtime 隱患：
1. **規格鏈級聯幻覺 (Cascading Specification Hallucination)**：
   - 規劃器（Planner）在規劃第四題時產生了幻覺（將遞增值從 1 改為 2）。
   - PromptBuilder 將其強制格式化為 `[REPAIR SPECIFICATION (MANDATORY)]`。
   - 執行器（Executor）受限於 `MANDATORY` 最高權威，被迫順從錯誤規格產生 `count += 2` 的錯誤 patch。即便 Verifier 報錯引導，仍卡在 Mandatory 約束下無法自拔。
2. **語意重試 (Semantic Retry) 被無聲阻斷**：
   - 模型在 attempt 1 產生了 valid 格式的 patch，但由於 logic regression，`compute_failure_class` 在判定錯誤類型時，誤將成功的 `VALID_SEARCH_REPLACE` 解析格式字串判定為 `parse_failed` 錯誤。
   - 這直接導致 `semantic_retry_evidence_ready` 被設為 `False`，使得系統完全沒有為此邏輯錯誤發起 semantic retry。
3. **哈希不一致 (Hash Mismatch) 噪音阻斷成功判定**：
   - 在隔離區套用成功後，`isolated_workspace_apply` 會對 `git diff` 輸出的 diff 內容計算 sha256，並與 `candidate_hash` 比對。由於 metadata 和空行等微小格式差異，兩者經常不一致（`hash_match=False`），使得即使 verifier 已經 pass (綠燈)，也會被當成 `hash_mismatch` 失敗封鎖。
4. **環境變數生命週期不一致**：
   - `run_core_row` 內部的 `finally` 區塊過早 pop 掉了 `NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER` 等變數，導致 executor 在實際呼叫 LLM 時回傳了 `provider_not_configured` 錯誤。
   - `OllamaLocalModelProvider` 僅讀取了 `NEXUS_LOCAL_MODEL_PROVIDER` 而不是 runner 所提供的 `NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER`。

---

## 2. 實作修復方案 (Regression Recovery)

我們執行了以下技術修復：
- **Prompt 結構化約束分級與權威順序**：修改 `prompt_builder.py` 的 prompt 結構，明確區分 `[VERIFIED CONSTRAINTS — MUST FOLLOW]` 與 `[PLANNER HYPOTHESIS — VERIFY AGAINST CODE]`，並新增 `[CODE AND VERIFIER TRUTH — HIGHEST FACTUAL AUTHORITY]` 引導模型在規格衝突時以代碼與 verifier 為準，防止全域降權可能造成的約束失效。
- **排除成功格式的 parse_failed 誤判**：修改 `local_model_executor.py` 裡的 `compute_failure_class`，排除對 `VALID_SEARCH_REPLACE` 的 `parse_failed` 判定。同時補齊了 negative tests 確保真正錯誤格式依然被判定為 parse_failed，成功喚醒語意重試。
- **實作嚴謹的 Canonical Diff Hash 比對與對齊**：修改 `isolated_workspace_apply.py`，採用 `canonicalize_diff` 規整行尾空白與 git metadata。若比對 matches 為 `True`，則將 `applied_patch_hash` 設為與 `selected_candidate_hash` 一致，完美消除 metadata 格式噪音，且保留了 candidate / receipt integrity 安全判定。
- **防止環境變數跨 Row 洩漏的還原機制**：修改 `n30r_v2_runner.py` 裡的 `run_core_row`，在執行前備份環境變數，並使用 `try...finally` 機制在執行後 100% 強制恢復原始狀態，防止 nested 執行污染。
- **相容環境變數讀取**：在 `local_model_provider.py` 中支援讀取 `NEXUS_LOCAL_MODEL_EXECUTOR_PROVIDER` 環境變數。

---

## 3. Canonical Paired Evaluation 驗證數據

我們重跑了完整 8-row paired evaluation (4 tasks * 2 arms)，產生的數據已被妥善封存：
- **JSONL Results**: `docs/bench/n30r/v2_paired_results_canonical.jsonl`
- **Summary Metrics**: `docs/bench/n30r/v2_paired_summary_canonical.json`

### 結論與 Seal：
```text
ARMOR_RECOVERED_NEUTRAL

Bare: 4/4
Armor: 4/4
Solve delta: 0
No solve-rate uplift

Correctness regression eliminated.
Canonical run did not exercise semantic retry.
Prior diagnostic runs demonstrated semantic retry capability separately.

Bare mean latency: 5.66s
Armor mean latency: 20.42s
Armor latency multiplier: 3.61x
```

本次修復完全消除了先前 V2 harness 的 Regression 退化，將系統成功收尾於預期狀態！
報告人：Nexus 戰甲工程師
驗證時間：2026-07-11
