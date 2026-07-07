# C6AZ: Apply Mismatch Forensics

**Date**: 2026-07-07
**Task**: C6AZ-apply-mismatch-forensics
**Scope**: This task is forensic-only. No behavior-changing patch shipped. Single minimal patch candidate only.

---

## 1. 問題摘要

C6AX and C6AY both confirmed D/A committee fully executes, and C6AY confirmed diagnosis guidance changes candidate content (hash changed `5f77624a` → `83ca2994`). However, both runs fail at the same point: `patch_apply_failed` at `astropy/table/table.py:4`. This forensic task determines the single primary root cause of the apply failure.

---

## 2. C6AX vs C6AY Candidate 對照表

| Metric | C6AX | C6AY |
|---|---|---|
| `diagnosis_guidance_injected` | N/A | True |
| winner candidate_hash | `5f77624a...` (raw `0220bb06...`) | `83ca2994...` (raw `19ea00af...`) |
| winner model | qwen2.5-coder:7b-instruct | qwen2.5-coder:7b-instruct |
| `isolated_apply_status` | **failed** | **failed** |
| `isolated_apply_error` | `patch failed: astropy/table/table.py:4` + `patch does not apply` | **identical** |
| `patch_lifecycle_state` | `isolation_attempted_apply_failed` | **identical** |
| `failure_class` | `patch_apply_failed` | **identical** |
| `solved` | False | False |
| same anchor? | Yes — both target `astropy/table/table.py:4` | Yes |
| same failure point? | Yes — `patch does not apply` at line 4 | Yes |


---

## 3. Apply Failure Taxonomy

**Primary root cause: `search_span_mismatch`**

Evidence chain:
1. **Apply error (both runs)**: `error: patch failed: astropy/table/table.py:4\nerror: astropy/table/table.py: patch does not apply`
2. **locked_search (from benchmark spec)**: `if hasattr(data, 'dtype') and len(getattr(data, 'dtype', [])) > 1:\n            self._data = data.view(type('NdarrayMixin', (), {'__array__': lambda self: self._data})())`
3. **Real source file** (`artifacts/external_sources/astropy_13236/astropy/table/table.py`, 4247 lines):
   - Line 4: `import types` (NOT the locked_search content)
   - Line 48: `from .ndarray_mixin import NdarrayMixin  # noqa: F401` (import only)
   - Line 686: `def __init__(` (Table.__init__, real location)
   - Line 1366: `elif not hasattr(data, "dtype"):` (different syntax from locked_search)
   - `grep "if hasattr(data, 'dtype')"` → **0 matches** in real source
4. **locked_search does NOT exist in real source file** — it is synthetic code from benchmark's `buggy_code` field
5. **Forensic classifier**: `forensic_apply_mismatch(...)` → **`search_span_mismatch`**

---

## 4. 代碼/產物證據

### Forensic helper (new, forensic-only)

| File | Lines | Change |
|---|---|---|
| `local_model_executor.py` | 365-411 | `forensic_apply_mismatch()` — maps apply error + locked_search + source to single taxonomy root cause |

### Tests (6 passed, RED→GREEN)

| Test | Taxonomy class |
|---|---|
| `test_locked_search_absent_from_source_classifies_as_search_span_mismatch` | search_span_mismatch |
| `test_corrupt_patch_classifies_as_syntax_shape_invalid` | syntax_shape_invalid |
| `test_wrong_target_file_classifies_correctly` | wrong_target_file |
| `test_partial_match_classifies_as_partial_match_but_anchor_rejected` | partial_match_but_anchor_rejected |
| `test_unknown_error_classifies_as_unknown` | unknown_apply_failure |
| `test_c6ax_c6ay_both_classify_as_search_span_mismatch` | C6AX/C6AY verification |

### Source file evidence

```
$ grep -n "if hasattr(data, 'dtype')" astropy/table/table.py
(empty — 0 matches)

$ grep -n 'NdarrayMixin' astropy/table/table.py
48:from .ndarray_mixin import NdarrayMixin  # noqa: F401

$ head -10 astropy/table/table.py

---

## 5. 最小 Patch Candidate

**Single minimal patch candidate: `target-region grounding patch`**

The locked_search provided to the model doesn't match any content in the real source file. The model faithfully generates a SEARCH/REPLACE patch using this wrong span, but `git apply` fails because the SEARCH block doesn't exist in the file.

The fix is to ground the locked_search in actual source file content — extract the real code span around the target symbol (`Table.__init__` at line 686+) from the source file, instead of using the synthetic `buggy_code` snippet.

---

## 6. Next Automatic Action

```
Next automatic action:
Do C6BB-target-grounding-minimal-patch: replace the benchmark's synthetic
locked_search for astropy__astropy-13236 with the actual source code span
around Table.__init__ (line 686+) extracted from
artifacts/external_sources/astropy_13236/astropy/table/table.py, then re-run
the same task to verify the patch applies. Do not change committee wiring,
diagnosis, or A-phase.
```

---

## Appendix: Files Touched (3, within max 8)

| File | Change |
|---|---|
| `nexus/services/local_heal/local_model_executor.py` | `forensic_apply_mismatch()` helper (+47 lines, forensic-only) |
| `tests/unit/local_heal/test_c6az_apply_mismatch_forensics.py` | 6 new tests (NEW file) |
| `docs/reports/c6az_apply_mismatch_forensics.md` | This report (NEW) |

**Tests**: 50 passed (6 C6AZ + 10 C6AY + 11 C6AW + 8 C6AV + 15 existing), 0 failed
**No live rerun needed** — artifacts from C6AX/C6AY logs + JSONL + real source file were sufficient
**No behavior-changing patch shipped. Forensic-only. Single minimal patch candidate only.**

# Licensed under a 3-clause BSD style license - see LICENSE.rst
import itertools
import sys
import types          ← line 4, where patch fails
```

**Key finding**: candidate content changed (different hash), but anchor and failure point are identical.
