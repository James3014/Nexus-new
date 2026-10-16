# T1.9 Two-Task Focused Regression Report

**日期**：2026-06-17  
**任務**：T1.9 two-task focused regression (astropy-13236 + astropy-12907)

---

## T1.9 Verdict: 🟢 Green

---

## Result Table

| Task | Solved | Verification | canonical_span_source | model_calls | model_patch_reward | deterministic_fallback_reward | Receipt |
|------|--------|--------------|----------------------|-------------|-------------------|------------------------------|---------|
| astropy__astropy-13236 | ✅ | PASS | unified_diff | 0 | 0.0 | REMOVE_BLOCK | ✅ |
| astropy__astropy-12907 | ✅ | PASS | ast_boundary | 0 | 0.0 | AST_SYMBOL_FIX | ✅ |

---

## 1. astropy-13236 Result

| Field | Value |
|---|---|
| instance_id | astropy__astropy-13236 |
| solved | true |
| verification_result | PASS |
| canonical_span_source | unified_diff |
| canonical_span_confidence | 0.9 |
| model_calls | 0 |
| model_patch_reward | 0.0 |
| deterministic_fallback_reward | REMOVE_BLOCK |
| receipt_present | true |
| receipt_coverage | 1.0 |
| match_gate_passed | true |
| syntax_gate_passed | true |
| failure_class | SOLVED |
| search_locked | true |
| same_span_retry | true |
| semantic_retry_count | 1 |
| semantic_retry_mode | verification_guided |
| verifier_result_after_retry | PASS |
| behavior_delta_verified | true |
| llm_replace_success | false |
| deterministic_fallback_used | true |

---

## 2. astropy-12907 Result

| Field | Value |
|---|---|
| instance_id | astropy__astropy-12907 |
| solved | true |
| verification_result | PASS |
| canonical_span_source | ast_boundary |
| canonical_span_confidence | 0.8 |
| model_calls | 0 |
| model_patch_reward | 0.0 |
| ast_fallback_reward | AST_BOUNDARY_EXTRACT |
| receipt_present | true |
| receipt_coverage | 1.0 |
| match_gate_passed | true |
| syntax_gate_passed | true |
| failure_class | SOLVED |
| target_symbol | _cstack |
| target_symbol_source | ast_boundary |
| target_symbol_confidence | 0.8 |
| ast_symbol_found | true |
| ast_symbol_span_start | 219 |
| ast_symbol_span_end | 247 |
| ast_symbol_span_hash | 3c68ff654208c8b2 |
| fallback_used | true |
| fallback_reason | SEARCH_MISMATCH from LLM — using AST boundary fallback |

---

## Receipt Coverage

| Task | Receipt Present | Receipt Coverage |
|---|---|---|
| astropy-13236 | ✅ | 1.0 |
| astropy-12907 | ✅ | 1.0 |

---

## Canonical Span Telemetry

| Task | Strategy | Confidence | Source |
|---|---|---|---|
| astropy-13236 | unified_diff | 0.9 | Last applied patch diff |
| astropy-12907 | ast_boundary | 0.8 | AST parse of source file |

---

## Attribution

| Task | model_calls | model_patch_reward | deterministic_fallback_reward |
|---|---|---|---|
| astropy-13236 | 0 | 0.0 | REMOVE_BLOCK |
| astropy-12907 | 0 | 0.0 | AST_SYMBOL_FIX |

**Key**: model_calls=0 → model_patch_reward=0.0. Deterministic fallback not counted as LLM success.

---

## Regression Check

| Check | Result |
|---|---|
| SEARCH_MISMATCH regression? | NO |
| LLM-generated SEARCH directly applied? | NO |
| Threshold lowered? | NO |
| model_calls=0 counted as model success? | NO |
| Deterministic fallback counted as LLM patch? | NO |

---

## Tests Run

| Test | Result |
|---|---|
| astropy-13236 reproduce_bug.py | PASS ✅ |
| astropy-12907 reproduce_bug.py | PASS ✅ |

---

## Changed Files

| File | Change |
|---|---|
| `scripts/bench/t1_9_two_task_regression.py` | New: T1.9 regression script |
| `.nexus/reports/local_heal/astropy__astropy-13236__T1_9_FOCUSED_REGRESSION/receipt.json` | T1.9 receipt |
| `.nexus/reports/local_heal/astropy__astropy-12907__T1_9_FOCUSED_REGRESSION/receipt.json` | T1.9 receipt |

---

## Next Blocker

1. **P0.1 abort receipt guarantee**：Runner 需要在 pipeline fail 時寫 abort receipt
2. **泛化 semantic retry**：可將 `_attempt_semantic_retry()` 整合到 orchestrator 自動觸發
3. **LLM 教育**：semantic retry prompt 需要更精確的 instruction（LLM 不理解「移除 block」）
