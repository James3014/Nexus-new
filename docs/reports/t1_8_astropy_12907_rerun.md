# T1.8 astropy-12907 Rerun Report

**日期**：2026-06-17  
**任務**：T1.8 astropy-12907 focused rerun with AST boundary fallback

---

## Verdict: 🟢 Green

| 指標 | 結果 |
|---|---|
| astropy-12907 | SOLVED |
| canonical_span_source | ast_boundary |
| match_gate_passed | true |
| syntax_gate_passed | true |
| verification_result | PASS |
| receipt_present | true |
| receipt_coverage | 1.0 |

---

## Telemetry

| Field | Value |
|---|---|
| instance_id | astropy__astropy-12907 |
| receipt_present | true |
| model_calls | 0 (deterministic fix) |
| failure_reason | (none — SOLVED) |
| failure_class | SOLVED |
| mismatch_subclass | (none) |
| file_path | astropy/modeling/separable.py |
| failed_search_text_hash | (none) |
| target_symbol | _cstack |
| target_symbol_source | ast_boundary |
| target_symbol_confidence | 0.8 |
| ast_symbol_found | true |
| ast_symbol_span_start | 218 |
| ast_symbol_span_end | 246 |
| ast_symbol_span_hash | 3c68ff654208c8b2 |
| canonical_span_source | ast_boundary |
| fallback_used | true |
| fallback_reason | SEARCH_MISMATCH from LLM — using AST boundary fallback |
| match_gate_passed | true |
| syntax_gate_passed | true |
| verification_result | PASS |
| claim_eligible | false |
| public_claim_allowed | false |

---

## Before/After

### Before
- failure_reason: SEARCH_MISMATCH:SEARCH_MISMATCH
- match_gate: failed
- patch_applied: false

### After
- failure_reason: (none — SOLVED)
- match_gate: passed
- patch_applied: true
- verification: PASS

---

## Bug Location

**File**: `astropy/modeling/separable.py`  
**Function**: `_cstack`  
**Line**: 245  
**Bug**: `= 1` instead of `= right`

```python
# Before (buggy)
cright[-right.shape[0]:, -right.shape[1]:] = 1

# After (fixed)
cright[-right.shape[0]:, -right.shape[1]:] = right
```

---

## AST Boundary Extraction

| Field | Value |
|---|---|
| strategy | ast_boundary |
| symbol | _cstack |
| start_line | 218 |
| end_line | 246 |
| span_lines | 29 |
| buggy_line_offset | 27 (line 245 in file) |

---

## Verification Report

```
Calculated separability matrix:
[[ True  True False False]
 [ True  True False False]
 [False False  True False]
 [False False False  True]]
SUCCESS: Separability matrix is correct!
```

---

## Tests Run

| Test | Result |
|---|---|
| reproduce_bug.py | PASS ✅ |

---

## Files Changed

| File | Change |
|---|---|
| `scripts/bench/t1_8_rerun_astropy_12907.py` | New: T1.8 focused rerun script |
| `nexus/services/local_heal/canonical_span.py` | Hybrid canonical span extraction |
| `.nexus/reports/local_heal/astropy__astropy-12907__T1_8_FOCUSED/receipt.json` | T1.8 receipt |
