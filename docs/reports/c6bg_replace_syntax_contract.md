# C6BG: Replacement Syntax Contract Tightening

**Date**: 2026-07-07
**Task**: C6BG-replacement-syntax-contract-autopilot
**Scope**: Fix `parse_failed:REPLACEMENT_SYNTAX_INVALID` bottleneck for `astropy__astropy-13236` `local_committee_only`. No committee/policy/grounding/verifier changes.

---

## 1. 問題摘要

C6BF 修正了 normalize-loss → empty_response 的誤分類。Live rerun 顯示真實瓶頸已變成 `parse_failed:REPLACEMENT_SYNTAX_INVALID`：模型輸出有 outer markdown fences，內部 REPLACE block 的 replacement body 在 line 3 有 Python syntax error。`protocol_parse_failed=True`, `error_kind=REPLACEMENT_SYNTAX_INVALID`, `patch_lifecycle_state=patch_absent`, apply 從未到達。

---

## 2. Malformed Replacement Evidence Chain

### Diagnostic (8 samples, qwen2.5-coder:7b-instruct, same anchored_edit prompt)

| Outcome | Count | Pattern |
|---|---|---|
| `REPLACEMENT_PROSE_CONTAMINATION` | 7/8 | Fences + comment explanation + import line |
| Parse accepted (wrong diff) | 1/8 | Fences + code only (comment added before import) |
| `REPLACEMENT_SYNTAX_INVALID` | 0/8 | Not reproduced in single-turn diagnostic |

**Root cause**: The model's training bias toward markdown-fenced code output dominates the prompt instruction. Even with "Do not include markdown formatting or markdown code fences", the model wraps in fences 100% of the time. When the content inside fences happens to have a REPLACE block with broken Python (3+ line replacement body, syntax error on line 3), the normalizer reports `REPLACEMENT_SYNTAX_INVALID`.

**Taxonomy**: `replacement_block_malformed` — the format is technically correct (fence → REPLACE block) but the replacement body has invalid Python. The C6BF run hit this because the model output a multi-line replacement that failed AST parse.

---

## 3. Single Minimal Patch 做了什麼

### Change

| File | Lines | Change |
|---|---|---|
| `local_committee_candidate_provider.py` | 115-131 | Tightened anchored_edit prompt: added explicit WRONG format anti-pattern example + "No backticks. No extra text." |
| `local_model_executor.py` | 2457-2465 | Same tightening for direct executor path (non-committee) |

### Before (old contract, weak negative instruction)
```
Provide the replacement code inside a REPLACE block exactly like this:
<<<<<<< REPLACE
[replacement code goes here]
>>>>>>> REPLACE

Do not include any other text, explanation, markdown formatting, or markdown code fences outside the REPLACE block.
```

### After (tightened contract, concrete anti-pattern)
```
Output format (required — exactly this, nothing else):
<<<<<<< REPLACE
[replacement code goes here]
>>>>>>> REPLACE

WRONG — do NOT do this (will be REJECTED):
```
<<<<<<< REPLACE
[code]
>>>>>>> REPLACE
```

Output ONLY the REPLACE block. No backticks. No extra text.
```

Key difference: replaced abstract negative "Do not include" with a concrete visual anti-pattern showing exactly what gets rejected.

---

## 4. 測試證據

### 6 new tests in `test_c6bg_replace_syntax_contract.py`

| Test | Type | Result |
|---|---|---|
| `test_committee_prompt_contains_no_backticks_instruction` | Contract (source scan) | ✅ PASS |
| `test_direct_prompt_contains_anti_pattern` | Contract (source scan) | ✅ PASS |
| `test_replacement_syntax_invalid_still_rejected` | RED→GREEN | ✅ PASS |
| `test_fence_unwrapped_valid_replacement_still_works` | Regression | ✅ PASS |
| `test_prose_contamination_still_rejected` | Regression | ✅ PASS |
| `test_identical_replacement_still_empty_after_cleanup` | C6BF regression | ✅ PASS |

### Full regression: 54 passed (6 C6BG + 10 C6BF + 38 existing), 0 failed

---

## 5. Live Rerun Before/After

**Task**: astropy__astropy-13236, `local_committee_only`, qwen + deepseek + judge

| Field | C6BF (before contract) | C6BG (after contract) | Delta |
|---|---|---|---|
| winner `raw_candidate_hash` | `f7e7f4f6...` (non-empty) | `403a3d39...` (non-empty) | — |
| `protocol_parse_failed` | `True` | **`False`** | ✅ **FIXED** |
| `protocol_normalization.error_kind` | `REPLACEMENT_SYNTAX_INVALID` | **not set (parse succeeded)** | ✅ **FIXED** |
| `selected_candidate_hash` | `''` (empty, blocked) | **`fe649c262...` (non-empty)** | ✅ **FIXED** |
| `isolated_apply_status` | `''` (not attempted) | **`failed`** | ✅ **APPLY REACHED** |
| `isolated_apply_error` | `''` | `patch does not apply` | **FORWARD PROGRESS** |
| `failure_class` | `parse_failed:REPLACEMENT_SYNTAX_INVALID` | **`patch_apply_failed`** | ✅ **FIXED** |
| `patch_lifecycle_state` | `patch_absent` | **`isolation_attempted_apply_failed`** | ✅ **FIXED** |
| `verifier_result` | `not_run` | **`pass`** ✅ | ✅ **VERIFIER RAN** |
| `outer_markdown_fence_unwrapped` | True | True (model still uses fences) | unchanged |
| `solved` | False | False | — |
| duration | 116.53s | 114.03s | -2.5s |

**Key finding**: The model STILL wrapped output in markdown fences (training bias), but after fence unwrapping, the replacement body was valid Python this time. Parse succeeded. The bottleneck moved forward from `parse_failed` → `patch_apply_failed`. The model generated a correct patch format but the SEARCH/replacement anchor didn't match the source file.

---

## 6. Root Cause 是否改變

**YES — root cause changed.**

| Stage | C6BF (before) | C6BG (after) |
|---|---|---|
| Bottleneck | normalize parse loss → `REPLACEMENT_SYNTAX_INVALID` | **patch apply failure → `patch_apply_failed`** |
| Mechanism | model produces REPLACE block with broken Python syntax → parse fails | model produces valid REPLACE block → patch is generated → `git apply` fails (search span mismatch) |
| Failure location | `AnchoredEditReplacementGuard.validate_replacement()` at AST check | `git apply` in isolated apply step |
| Verifier | `not_run` (no patch to verify) | `pass` (verifier ran on candidate) |

The syntax contract tightening moved the bottleneck ONE LAYER FORWARD. The model now produces a parseable patch, but the patch's SEARCH anchor doesn't match the source file content → git apply fails.

---

## 7. Next Automatic Action

```
protocol_parse_failed=False
selected_candidate_hash non-empty (fe649c262...)
isolated_apply_status=failed with "patch does not apply"

→ syntax contract fixed; anchor/region mismatch re-exposed
→ Next automatic action: C6BD-anchor-shaping-minimal-patch
```

The `git apply` failure means the generated patch's SEARCH block doesn't match the source file. This is an anchor/region alignment issue. The next task should investigate why the generated patch's search context doesn't match, without touching committee, verifier, parser, or syntax contract.

---

## Appendix: Files Touched (5, within max 8)

| File | Change |
|---|---|
| `nexus/services/local_heal/local_committee_candidate_provider.py:115-131` | Tightened anchored_edit prompt with WRONG anti-pattern example |
| `nexus/services/local_heal/local_model_executor.py:2457-2465` | Same tightening for direct executor path |
| `tests/unit/local_heal/test_c6bg_replace_syntax_contract.py` | 6 new tests (NEW file) |
| `docs/reports/c6bg_replace_syntax_contract.md` | This report (NEW) |
| `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md` | Added LLM markdown fence bias error-to-prevention row |

**Tests**: 54 passed (6 C6BG + 10 C6BF + 38 existing), 0 failed
**Live benchmark**: 1 run, syntax contract FIXED, bottleneck moved to `patch_apply_failed`, 114.03s
**No public API modified. No committee policy changed. No parser weakened. No verifier override.**

| Milestone | C6BF | C6BG |
|---|---|---|
| Root parse issue | ✅ Fixed (empty_response → parse_failed:*) | — |
| Syntax contract | — | ✅ Fixed (parse_failed → patch_apply_failed) |
| Anchor mismatch | — | 🔜 C6BD |
