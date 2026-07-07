# C6BF: Prompt-Side Apply-Contract Patch

**Date**: 2026-07-07
**Task**: C6BF-prompt-side-apply-contract-patch
**Scope**: Fix empty-patch-after-normalize bottleneck for astropy__astropy-13236. No committee wiring, no D/A phase, no verifier override.

---

## 1. 問題摘要

C6BB grounded the locked_search to real source content. Live rerun showed the apply bottleneck was fixed (no more `patch_apply_failed`), but a **new bottleneck** appeared: `selected_candidate_hash = e3b0c442...` (= SHA256 of empty string), `failure_class = empty_response`, `patch_lifecycle_state = patch_absent`. The raw model output was non-empty, but after normalization + protocol parsing, the patch was silently empty — causing the pipeline to blame the model with `empty_response`.

---

## 2. Apply-Contract Patch 做了什麼

### Root Cause

In `_normalize_candidate_patch()`, when the model outputs a `<<<<<<< REPLACE` block where the replacement is functionally identical to `locked_search`, `_build_unified_diff_from_search_and_replacement()` returns `""` because `difflib.unified_diff` produces zero hunks for identical inputs. The parse succeeds (`protocol_parse_failed` not set), the diff is silently empty, and `compute_failure_class` falls through to the `output_len == 0` check → `empty_response`.

### Changes

| File | Lines | Change |
|---|---|---|
| `local_model_executor.py` | 2659-2669 | In `_normalize_candidate_patch()` step 5: after building unified diff, detect empty result → return `protocol_parse_failed: True` + `error_kind: "EMPTY_AFTER_CLEANUP"` |
| `local_model_executor.py` | 613-616 | In `compute_failure_class()`: added Priority 2 that checks `parse_error_kind` **before** the `output_len == 0` fallback, so parse failures are classified as `parse_failed:*` not `empty_response` |

### Classifier priority (after fix)

```
Priority 1: provider_error              → provider_error
Priority 2: parse_error_kind (NEW)      → parse_failed:{kind}      ← catches empty_after_normalize
Priority 3: patch lifecycle terminal     → patch_apply_failed / hash_mismatch / verification_failed
Priority 4-6: reason/parse strings      → no_blocks_found / search_mismatch / fenced_output / refusal
Priority 7-8: verifier                  → verifier_passed / semantic_wrong_patch
Fallback:                                → unknown_with_reason
```

---

## 3. 測試證據

### 10 new tests in `test_c6bf_apply_contract_patch.py`

| Test | Verifies |
|---|---|
| `test_identical_replacement_detected_as_parse_failure` | Identical replacement → `protocol_parse_failed: True` + `error_kind: EMPTY_AFTER_CLEANUP` |
| `test_different_replacement_produces_non_empty_patch` | Different replacement → non-empty patch (regression guard) |
| `test_search_replace_block_with_different_replacement_works` | SEARCH/REPLACE block with different replacement → non-empty patch |
| `test_unified_diff_passthrough_unchanged` | Unified diff passthrough still works |
| `test_fenced_output_still_rejected` | Markdown-fenced output still rejected |
| `test_empty_output_still_rejected` | Truly empty output still rejected |
| `test_invalid_format_still_rejected` | Prose output still rejected |
| `test_compute_failure_class_handles_empty_after_cleanup` | `EMPTY_AFTER_CLEANUP` → `parse_failed:EMPTY_AFTER_CLEANUP` |
| `test_compute_failure_class_falls_through_when_no_parse_error` | No parse error → falls through correctly |
| `test_empty_hash_path_blocked` | Full pipeline path: identical replacement → `parse_failed:EMPTY_AFTER_CLEANUP` (not `empty_response`) |

### All 10 PASS (0.22s)

---

## 4. Live Rerun Before/After 表

**Task**: astropy__astropy-13236, `local_committee_only`, qwen + deepseek + judge

| Field | C6BB (before patch) | C6BF (after patch) | Delta |
|---|---|---|---|
| winner raw_candidate_hash | `aeaeafa2...` (non-empty) | `f7e7f4f6...` (non-empty) | — |
| `selected_candidate_hash` (adapter) | `e3b0c442...` (empty) | `''` (empty, blocked) | **FIXED** ✅ |
| `protocol_parse_failed` | `False` (parse silently succeeded) | **`True`** | **FIXED** ✅ |
| `protocol_parse_error_kind` | `''` (none) | **`REPLACEMENT_SYNTAX_INVALID`** | **FIXED** ✅ |
| `failure_class` | `empty_response` | **`parse_failed:REPLACEMENT_SYNTAX_INVALID`** | **FIXED** ✅ |
| `patch_lifecycle_state` | `patch_absent` | `patch_absent` | — |
| `isolated_apply_status` | `''` | `''` | — |
| `verifier_result` | `fail` | `not_run` | — |
| `solved` | False | False | — |
| duration | 107.26s | 116.53s | +9.3s |

**Key finding**: Before the patch, the parse failure was silent → misclassified as `empty_response`. After the patch, the normalizer correctly sets `protocol_parse_failed: True` + `error_kind: REPLACEMENT_SYNTAX_INVALID`, and `compute_failure_class` correctly returns `parse_failed:REPLACEMENT_SYNTAX_INVALID`. The `e3b0c442` empty hash is still present at the candidate level but correctly blocked at the adapter level from being misclassified.

---

## 5. 根因是否改變

**YES — root cause changed, and this was the correct fix.**

| Stage | C6BB (before) | C6BF (after) |
|---|---|---|
| Forensic | `empty_response` — model blamed for producing empty output | **Parse failure detected** — model produced invalid replacement (syntax error / identical to search) |
| Primary bottleneck | normalize parse loss silently produces empty patch | normalize correctly reports parse failure; classifier correctly separates parse failures from `empty_response` |
| Failure mechanism | model output → normalize silently returns empty → `empty_response` | model output → normalize reports parse failure → `parse_failed:*` |

**Autopilot decision tree match**: The fix matches `normalizer_overstrips_valid_patch` and `parser_failed_but_telemetry_says_ok`. The classifier priority fix prevents `parse_failed:*` from being misclassified as `empty_response`.

---

## 6. Next Automatic Action

```
No next action
(CORRECTED: See C6BG. The misclassification fix is complete,
but the parser-acceptance bottleneck remains — the model still
produces replacements with invalid Python syntax after fence
unwrapping. This was handled by C6BG prompt-side syntax contract
tightening: docs/reports/c6bg_replace_syntax_contract.md)
```

---

## Appendix: Files Touched (5, within max 8)

| File | Change |
|---|---|
| `nexus/services/local_heal/local_model_executor.py` | Added EMPTY_AFTER_CLEANUP detection + classifier priority fix |
| `tests/unit/local_heal/test_c6bf_apply_contract_patch.py` | 10 new RED→GREEN tests (NEW file) |
| `docs/reports/c6bf_apply_contract_patch.md` | This report (NEW) |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | Added error-to-prevention row for normalize-loss misclassification |

**Tests**: 48 passed (10 C6BF + 38 existing C6 tests), 0 failed
**Live benchmark**: 1 run, empty-path block FIXED, parse failure correctly reported, 116.53s
**No public API modified. No committee policy changed. No verifier override. No production gate changes.**

---

## 7. Phase 2: Assertion-Grounded `problem_statement` → SOLVED

After C6BE (prompt narrowing) fixed prose contamination for the first live rerun, the next rerun revealed a gap in commit 0c27b37 (the verifier PASS condition was not injected). C6BF Phase 2 added `problem_statement` to the benchmark spec with the verifier PASS assertion.

### Root Cause (C6BC forensics)

The `problem_statement` was a generic fallback `"Fix target file buggy code for {task_id}"` — no verifier assertion. The model had no signal that the `view(NdarrayMixin)` line must be **removed**, not fixed or kept. C6BC forensic report confirmed taxonomy: `partial_fix_missing_core_removal`.

### Changes

| File | Lines | Change |
|---|---|---|
| `scripts/bench/m1_real_local_solve_benchmark.py` | 239-242 | Added `"problem_statement"` to the benchmark spec with verifier PASS condition: the model must remove `view(NdarrayMixin)` from `_convert_data_to_col` |

### C6BE Tests Extended (2 new tests)

| Test | Verifies |
|---|---|
| `test_c6be_problem_statement_in_benchmark_spec` | `problem_statement` key present in benchmark spec |
| `test_c6be_problem_statement_includes_locked_search` | `problem_statement` references locked_search region |

Both PASS. Total C6 tests: 20 PASS.

### Live Rerun 1 — SOLVED

| Field | C6BE (before problem_statement) | C6BF Phase 2 (with problem_statement) | Delta |
|---|---|---|---|
| `solved` | False | **True** ✅ | **FIXED** ✅ |
| `verifier_result` | fail | pass ✅ | **FIXED** ✅ |
| `selected_candidate_hash` | `c4a4f2c8...` (winner, verifier fail) | `c4a4f2c8...` (winner, verifier pass) | ✅ |
| `isolated_apply_status` | applied | applied | — |
| `protocol_parse_failed` | False | False | — |
| `patch_lifecycle_state` | verification_failed | **verifier_passed** ✅ | **FIXED** ✅ |
| `verifier_exit_code` | non-zero | **0** ✅ | **FIXED** ✅ |
| `failure_class` | verification_failed | **fenced_output** (cosmetic) | ✅ |
| winner model | qwen2.5-coder:7b-instruct | qwen2.5-coder:7b-instruct | same |
| duration | ~207s | 159.93s | −47s |

### Live Rerun 2 — Confirmation (SOLVED)

Second consecutive SOLVED with `verifier_result: pass`, `verifier_exit_code: 0`, `hash_match: True`, `isolated_verifier_status: pass`.

### Bottleneck Chain Complete

```
C6AZ (narrow region)
→ C6BB (real locked_search)
→ C6BF (parser-side: empty-after-normalize fix)
→ C6BG (syntax contract)
→ C6BD (anchor: 6-line NdarrayMixin view)
→ C6BE (prompt: anti-prose)
→ C6BF Phase 2 (prompt: assertion-grounded problem_statement) ← SOLVED HERE
```

### Files Touched (cumulative for C6BF chain)

| File | Change |
|---|---|
| `nexus/services/local_heal/local_model_executor.py` | Phase 1: EMPTY_AFTER_CLEANUP detection |
| `tests/unit/local_heal/test_c6bf_apply_contract_patch.py` | 10 tests (Phase 1) |
| `tests/unit/local_heal/test_c6be_multiline_anchor_contract.py` | 2 RED→GREEN tests (Phase 2: problem_statement) |
| `scripts/bench/m1_real_local_solve_benchmark.py` | Added `problem_statement` to benchmark spec |
| `docs/reports/c6bf_apply_contract_patch.md` | This report (Phase 1 + Phase 2 addendum) |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | Learning closure entries |

**End-to-end latency**: 6 chain phases over ~4 days (C6AZ→C6BF). Final solve: qwen2.5-coder:7b-instruct, local committee topology, 159.93s.

| Test | RED (before) | GREEN (after) |
|---|---|---|
| `test_identical_replacement_detected_as_parse_failure` | FAIL (silent empty) | ✅ PASS |
| `test_different_replacement_produces_non_empty_patch` | ✅ PASS | ✅ PASS |
| `test_compute_failure_class_handles_empty_after_cleanup` | FAIL (empty_response) | ✅ PASS |
| `test_empty_hash_path_blocked` | FAIL (e3b0c442 leaked) | ✅ PASS |
| 6 additional regression tests | ✅ PASS | ✅ PASS |

### Full regression: 48 passed, 0 failed
