# Candidate Patch Search Over Bounded Replacements Report (P3)

本報告總結 **P3 — Candidate Patch Search Over Bounded Replacements** 的設計與實作。

## 1. 核心設計與實現
我們建立了 [candidate_search.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/candidate_search.py)，實現了 `CandidatePatchSearcher` 引擎。
當控制平面接收到 anchored context 之後，可請求 LLM（7B）生成多個補丁候選（通常 $N=3$）。搜尋引擎會基於 deterministic pipeline 對這些候選進行篩選與排序：
1. **去重過濾**: 排除重複的 `replacement_text`，降低驗證開銷。
2. **語意套用檢驗**: 分別在沙盒/工作區中嘗試套用，排除語法/格式無效者。
3. **Verifier 門禁**: 執行確定性 pytest verifier。無 verifier 通過者絕對無法晉升。
4. **Compliance 門禁**: 執行 Schema 與 Compliance Check。
5. **選擇策略**: 選擇第一個完全通過上述門禁的 candidate，忽視模型自我信心評估。

## 2. 候選補丁 Metadata
每個候選皆分配並記錄：
- `candidate_id`
- `model`, `model_call_id`, `prompt_variant`
- `replacement_text_hash`
- `patch_apply_status`, `verifier_status`, `compliance_status`
- `failure_stage` (在全部失敗時回報，如 `parse_fail`, `apply_fail`, `verifier_fail`, `compliance_fail`)
- `selected`

## 3. 單元測試驗證
新建了 [test_candidate_search.py](file:///Users/jameschen/Workspace/nexus/tests/unit/local_heal/test_candidate_search.py) 驗證，包含：
- `test_candidate_search_first_success`
- `test_candidate_search_compliance_blocking`
- `test_candidate_search_no_verifier_blocks_success`

測試已 100% 通過。

最終狀態：**`P3_CANDIDATE_PATCH_SEARCH_READY`**
