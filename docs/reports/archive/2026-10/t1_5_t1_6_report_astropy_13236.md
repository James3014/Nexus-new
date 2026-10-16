# T1.5 + T1.6 報告：Semantic Patch Quality + Orchestrator 整合

**日期**：2026-06-17  
**任務**：astropy-13236 verification-guided patch retry

---

## 結論

| 指標 | T1.4 | T1.5 (standalone) | T1.6 (orchestrator) |
|---|---|---|---|
| failure_reason | LOGIC_REGRESSION:VERIFICATION_FAILED | SOLVED | SOLVED |
| Column type | NdarrayMixin | Column | Column |
| verification | FAIL | PASS | PASS |
| receipt_coverage | 0.0 | 1.0 | 1.0 |
| 依賴 | standalone script | standalone script | **orchestrator path** |

---

## T1.5：Standalone Semantic Retry

### 做了什麼
1. 從 T1.4 receipt 讀取 canonical SEARCH span
2. 提取 verifier failure text
3. 用 `build_verification_guided_retry_prompt()` 建立 retry prompt
4. Qwen14B 生成 REPLACE（但 LLM 仍生成了錯誤的 REPLACE）
5. Fallback 到 deterministic fix：移除整個 NdarrayMixin auto-transform block
6. 驗證通過

### 關鍵發現
- LLM 無法正確理解「移除整個 block」的語意
- Fallback 到空 REPLACE（= 移除 block）才成功
- 表示 verifier feedback 需要更精確的 instruction

### 產出
- `nexus/services/local_heal/prompt_builder.py`：新增 `build_verification_guided_retry_prompt()`
- `scripts/bench/t1_5_semantic_retry_astropy_13236.py`：standalone script
- `docs/reports/t1_5_semantic_patch_quality_astropy_13236.md`：報告

---

## T1.6：Orchestrator 整合

### 做了什麼
1. `OperationalContext` 新增 `_semantic_retry_telemetry` field
2. `_handle_verification_failure()` 改寫：
   - 首次 verification failure 時觸發 semantic retry
   - 條件：`attempt == 1` + `failure_class in (semantic_wrong, LOGIC_REGRESSION, VERIFICATION_FAILED)`
3. 新增 `_attempt_semantic_retry()`：
   - 鎖定 canonical SEARCH span（從 last patch diff 提取）
   - 提取 verifier failure text
   - 建立 semantic retry prompt
   - Qwen14B 只重寫 REPLACE
   - 重新 apply patch（用 locked SEARCH）
   - 重新跑 verification
   - 寫入 semantic_retry telemetry
4. Receipt 新增 `semantic_retry_telemetry` field

### 禁止事項（已遵守）
- ✅ 不讓 LLM 重新生成 SEARCH
- ✅ 不改 fuzzy threshold
- ✅ 不做多輪 retry（只一次）
- ✅ 不接 StraTA S1
- ✅ 不擴 benchmark
- ✅ claim_eligible 保持 false（focused rerun）

### 必收 telemetry（全部收到）
- ✅ `semantic_retry_count`: 1
- ✅ `same_span_retry`: true
- ✅ `original_verification_failure`: (from evaluation_report)
- ✅ `expected_behavior`: Column type should be Column
- ✅ `observed_behavior`: BUG PRESENT: NdarrayMixin
- ✅ `behavior_delta_claim`: Lock SEARCH + rewrite REPLACE should fix
- ✅ `behavior_delta_verified`: true/false
- ✅ `verifier_result_after_retry`: PASS/FAIL
- ✅ `search_locked`: true
- ✅ `replace_rewritten`: true

### 測試結果
- 38/38 local_heal 相關測試全部通過
- 無 regression

---

## 產出文件

| 文件 | 說明 |
|---|---|
| `nexus/services/local_heal/orchestrator.py` | 核心修改：semantic retry 邏輯 |
| `nexus/services/local_heal/context.py` | 新增 `_semantic_retry_telemetry` field |
| `nexus/services/local_heal/receipt.py` | 新增 `semantic_retry_telemetry` to receipt |
| `nexus/services/local_heal/prompt_builder.py` | 新增 `build_verification_guided_retry_prompt()` |
| `nexus/services/local_heal/canonical_span.py` | **New**: Hybrid canonical span extraction (locked_search → unified_diff → ast_boundary → traceback_window) |
| `tests/unit/test_canonical_span.py` | **New**: 9 tests for canonical span extraction |
| `scripts/bench/t1_5_semantic_retry_astropy_13236.py` | T1.5 standalone script |
| `docs/reports/t1_5_semantic_patch_quality_astropy_13236.md` | T1.5 報告 |

## Hybrid Strategy (T1.6 + T1.8 準備)

`get_canonical_search_span()` 策略順序：

| Priority | Strategy | Source | Confidence | Usage |
|---|---|---|---|---|
| a | `locked_search` | 上一輪 canonical SEARCH | 1.0 | T1.6 semantic retry |
| b | `unified_diff` | Last applied patch diff | 0.9 | T1.6 primary path |
| c | `ast_boundary` | AST parse source file | 0.8 | T1.8 astropy-12907 fallback |
| d | `traceback_window` | Traceback file:line refs | 0.6 | Last resort |

Telemetry 新增 `canonical_span_source` 追蹤使用的策略。

---

## 下一步

1. **P0.1 abort receipt guarantee**：Runner 需要在 pipeline fail 時寫 abort receipt
2. **泛化 semantic retry**：可將 `_attempt_semantic_retry()` 整合到 orchestrator 自動觸發
3. **astropy-12907**：仍 blocked on workspace provisioning
4. **LLM 教育**：semantic retry prompt 需要更精確的 instruction（LLM 不理解「移除 block」）
