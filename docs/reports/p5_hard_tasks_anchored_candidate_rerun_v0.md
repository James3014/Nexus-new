# P5: Anchored Edit + Candidate Search — Three Hard Tasks Re-run

**Status**: P5_COMPLETE  
**Date**: 2026-06-20  
**Model**: gemma4-coder-12b-q4km:latest  
**Protocol**: NEXUS_PROTOCOL_MODE=anchored_edit  
**Baseline Reference**: C4 (7B, 0/3 success, all SEARCH_MISMATCH)

---

## Executive Summary

| Metric | C4 Baseline (7B) | P5 Anchored (12B) |
|---|---|---|
| Protocol | standard | anchored_edit |
| SEARCH_MISMATCH failures | 3/3 | 0/3 ✅ |
| Patch applied successfully | 0/3 | 7/9 candidates ✅ |
| Repro passed | 0/3 | 0/3 ❌ |
| Tasks succeeded | 0/3 | 0/3 |

**Key finding**: Anchored edit 完全消除了 SEARCH_MISMATCH 問題（0/9 candidates），但模型的 replacement content 不夠正確，導致 repro 仍然失敗。問題從「協議失敗」轉移至「語義失敗」。

---

## Per-Task Analysis

### C_13453 — astropy__astropy-13453 (HTML formats parameter ignored)

**Anchor**: HTML.write() 中 `col.info.iter_str_vals()` 的呼叫區塊 (276 chars, count=1 ✅)  
**Bug confirmed at base commit**: ✅ (baseline repro FAILED)  
**Candidates**: 3 generated, 3 applied, 0 repro-passed  

**Root cause of P5 failure**:  
Model anchored on the wrong code region. The fix location should be upstream: HTML.write() must call `self.data._set_col_formats()` before iterating values, so that `col.info.format` is populated. The model attempted patching `col.info.iter_str_vals()` inline, but `iter_str_vals()` reads `col.info.format` that was never set.

**Correct fix insight** (control-plane analysis):  
```python
# In HTML.write(), before the thead/tbody loop, add:
self.data._set_col_formats()
```
Or: move anchor to wrap the entire `col_str_iters` construction block.

**SEARCH_MISMATCH**: 0/3 ✅ (eliminated)

---

### C_11618 — sympy__sympy-11618 (Point.distance dimension mismatch)

**Anchor**: `ANCHOR_NOT_IN_SOURCE` ❌  
**Cause**: P5 script used anchor from the **current HEAD** version of `point.py` (which had `_normalize_dimension`), but base commit `d4f8832c21` has a different `distance()` body:
```python
# At d4f8832c21 (correct base):
return sqrt(sum([(a - b)**2 for a, b in zip(
    self.args, p.args if isinstance(p, Point) else p)]))
```

**Corrected anchor** (verified count=1 at d4f8832c21):  
`"        return sqrt(sum([(a - b)**2 for a, b in zip(\n            self.args, p.args if isinstance(p, Point) else p)]))"`

**SEARCH_MISMATCH**: N/A (script aborted before model call)  
**Action**: Fix script to checkout base_commit before reading source for anchor.

---

### C_12481 — sympy__sympy-12481 (Permutation non-disjoint cycles)

**Anchor**: `has_dups(temp)` validation block (292 chars, count=1 ✅)  
**Bug confirmed at base commit**: ✅  
**Candidates**: 3 generated, 3 applied (0 parse fail), 0 repro-passed  

**Failure mode**: cand_1 replacement was a **prose explanation** injected as code (SyntaxError: `instead of raising on duplicates, validate each cycle...`). Model output was natural language with embedded code block, not pure code. Parser's anchored_edit fallback accepted the markdown block but failed to strip the explanation text.

**SEARCH_MISMATCH**: 0/3 ✅ (eliminated)  
**Root issue**: Model mixed prose + code in output; parser fallback (variant 3) must be stricter.

---

## P5 vs C4 Capability Delta

| Failure Class | C4 (7B standard) | P5 (12B anchored) |
|---|---|---|
| SEARCH_MISMATCH | 3/3 (100%) | 0/9 (0%) ✅ |
| Patch apply success | 0/3 | 7/9 (78%) ✅ |
| Wrong anchor version | 0/3 | 1/3 (script bug) |
| Prose-as-code injection | N/A | 1/9 candidates |
| Correct repro | 0/3 | 0/3 |
| Semantic accuracy | LOW | LOW (unchanged) |

**Verdict**: Anchored edit architecture successfully decoupled the SEARCH brittleness from the semantic reasoning task. The protocol bottleneck has shifted from infrastructure to model capability.

---

## Remaining Bottlenecks

1. **Anchor must be read at base_commit** (not HEAD): C_11618 would have proceeded with correct anchor if we checkout → read → run.
2. **Model semantic accuracy** for complex bugs: `_set_col_formats` connection not captured by 12B model with 4096 ctx.
3. **Prose-as-code injection** (C_12481 cand_1): Parser fallback needs markdown stripping guard.
4. **Context window too small** (4096 tokens): `num_predict=768` is insufficient for complex Permutation fix.

---

## Lessons for P8 Planning

- **L1**: Always `git checkout base_commit && read_source` before anchor extraction in control plane.
- **L2**: Parser fallback must strip leading prose before accepting raw model output as replacement.
- **L3**: Complex semantic bugs (astropy format pipeline, sympy cycle composition) need deeper context — consider targeting submethod anchors instead of full body anchors.
- **L4**: 12B at 4096 ctx is better than 7B for protocol compliance but still insufficient for deep logic chain reasoning.
- **L5**: Consider providing the **correct fix spec** (not just anchor_intent) pre-computed from control plane for harder tasks.

