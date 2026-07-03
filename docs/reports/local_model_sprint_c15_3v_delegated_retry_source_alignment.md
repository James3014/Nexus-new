# C15-3V: Delegated Retry Protocol Hardening / Current Source Alignment

**Commit**: PENDING
**Date**: 2026-07-03
**Status**: CLOSED — SEARCH_MISMATCH blocker eliminated; delegated retry now applies patches cleanly; next gate: Gate D (Verifier Logic)

---

## 1. Root Cause Analysis

### C15-3U Gate C Exit State
After C15-3U, the live run showed:
```
delegated_retry_stage = first_patch_parser_rejected
delegated_retry_status = SEARCH_MISMATCH
```

### Investigation
Traced the full call path:
1. `local_model_executor.py:1749` → `heal_ctx.repo_dir = request.repo_root` (original repo)
2. Primary pipeline apply + verifier run against an isolated workspace; executor restores `original_target_path` to buggy code after apply.
3. Delegated retry `HealPipeline.run(heal_ctx)` triggers `LocalizationPhase` → `GranularMethodLocalizer.rank_files()` → reads disk file (restore buggy code = correct)
4. `PatchSynthesisPhase` then calls `SurgicalContextBuilder.build_annotated_context()` which emits **line-number-annotated format** (`   1 | def double(x):\n   2 |     return x * 2`)
5. Model sees annotated context with instruction "do NOT include line numbers in SEARCH", but still produced a SEARCH block that failed to match verbatim — `first_patch_parser_rejected` / `SEARCH_MISMATCH`.

### Root Cause
`LocalizationPhase` reads disk content and feeds it through `SurgicalContextBuilder._format_lines()`, which adds `"{idx+1:4d} | "` prefixes. Even with the warning header, small 7B models occasionally copy the format verbatim or generate a subtly different SEARCH block that fails the exact-match check.

The canonical locked_search span (set by C15-3S reanchor) is the authoritative source truth — it is verbatim, no line numbers, no annotations.

---

## 2. Fix Applied

### Modified File
- [local_model_executor.py](file:///Users/jameschen/Workspace/nexus/nexus/services/local_heal/local_model_executor.py) (delegated retry `heal_ctx` initialization block)

### Change
Before invoking `HealPipeline.run(heal_ctx)`, pre-populate `heal_ctx.localized_files` with the `locked_search` canonical span:

```python
# C15-3V: Pre-populate localized_files with locked_search canonical span.
_locked_search_for_dr = str(route_ctx.get("locked_search") or "")
_dr_localized_files: list = []
if _locked_search_for_dr.strip() and request.target_file:
    _dr_localized_files = [(request.target_file, _locked_search_for_dr)]
heal_ctx = LegacyHealContext(
    ...
    localized_files=_dr_localized_files,
)
```

`LocalizationPhase.execute()` short-circuits when `ctx.op.localized_files` is non-empty (L110), so localization is bypassed. `PatchSynthesisPhase` then receives verbatim `locked_search` as source — no line-number annotations, exact canonical text.

---

## 3. Red Line Checklist

| Constraint | Status | Notes |
|:---|:---|:---|
| No new route/router/planner/topology | **PASSED** | Untouched |
| Do not edit `CapabilityPlanner` | **PASSED** | Untouched |
| Do not edit `HybridRouteDecision` | **PASSED** | Untouched |
| Do not edit verifier behavior | **PASSED** | Untouched |
| Do not edit candidate isolation behavior | **PASSED** | Untouched |
| No new retry loops | **PASSED** | No new loops added |
| No hardcoded toy logic | **PASSED** | Uses `route_ctx["locked_search"]` generically |
| Do not claim `solved=true` | **PASSED** | `solved=false` |

---

## 4. Evidence

### Unit Tests
```
uv run pytest tests/unit/local_heal/test_local_model_executor.py -k test_c15_3t -q
====================== 4 passed, 141 deselected in 1.22s =======================
```

### Live Benchmark (toy-math-solve, C15-3V run)
```
delegated_retry_stage:               first_patch_failed      (was: first_patch_parser_rejected)
delegated_retry_status:              SUCCESS                  (was: SEARCH_MISMATCH)
delegated_retry_failure_reason:      LOGIC_REGRESSION:VERIFICATION_FAILED
delegated_retry_provider_called:     True
delegated_retry_provider_prompt_len: 3183
delegated_retry_provider_model_name: qwen2.5-coder:7b-instruct
delegated_retry_provider_response_empty: False
delegated_retry_provider_response_len:   112
apply_failure_root_cause:            ""   (was: search_block_mismatch_current_source)
semantic_retry_invoked:              True
semantic_retry_output_class:         VALID_PATCH
semantic_retry_status:               VERIFIER_FAILED
semantic_retry_failure_reason:       verifier_fail_after_retry
semantic_retry_raw_response_excerpt: FILE: toy/math_util.py
<<<<<<< SEARCH
    return x * 2
=======
    return x if x == 0 else x * 2
>>>>>>> REPLACE
patch_lifecycle_state:   isolation_applied_hash_match_verifier_failed
verifier_result:         fail
solved:                  false
```

---

## 5. Gate Progress

| Gate | Before C15-3V | After C15-3V |
|:---|:---|:---|
| Route authority / enforcement | ✅ | ✅ |
| Primary pipeline reanchor | ✅ | ✅ |
| Apply gate | ✅ | ✅ |
| Candidate isolation | ✅ | ✅ |
| Hash match | ✅ | ✅ |
| Retry eligibility | ✅ | ✅ |
| Delegated retry provider call | ✅ | ✅ |
| Delegated retry provider response (non-empty) | ✅ | ✅ |
| **Delegated retry patch apply (no SEARCH_MISMATCH)** | ❌ SEARCH_MISMATCH | ✅ **CLEARED** |
| Verifier logic pass / solved | ❌ | ❌ (next gate) |

---

## 6. Next Steps → C15-3W
- `delegated_retry_status = SUCCESS` but `semantic_retry_status = VERIFIER_FAILED`.
- Semantic retry patch excerpt: `return x if x == 0 else x * 2` — logically wrong (`x if x == 0` always returns `0`).
- The model's logic repair is incorrect; `toy-math-solve` task requires a **specific logical fix** to `double()`.
- C15-3W should verify: what exactly does `toy-math-solve` verify? What is the expected correct fix? Is the verifier output available in telemetry?

---

## 7. Explicit Non-Claims
- NOT solved (`verifier_result = fail`, `solved = false`).
- NOT local armor ready.
- NOT production ready.
- NOT public claim allowed.
