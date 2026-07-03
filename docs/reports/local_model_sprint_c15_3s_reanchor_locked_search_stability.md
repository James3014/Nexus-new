# C15-3S: Reanchor / Locked Search Stability — Closure Report

**Commit**: `bae86a438`
**Date**: 2026-07-03
**Status**: CLOSED — Gate A/B/C/D all cleared; next gate E → C15-3T

---

## Root Cause

`_reanchor_pipeline_patch_to_locked_search` read `current_text` from disk
**after** `HealPipeline` had already patched and written the target file.

Failure path (before fix):
- `locked_search = "def double(x):\n    return x * 2"`
- `HealPipeline.run()` writes modified content to `toy/math_util.py`
- `_reanchor_pipeline_patch_to_locked_search` reads `current_text` (now modified)
- `locked_search.strip() not in current_text` → early return `False`
- `pipeline_locked_search_reanchored: False`
- `candidate_patch` still has stale SEARCH block
- `run_isolated_workspace_apply` → apply_failure
- `apply_failure_root_cause: search_block_mismatch_current_source`

The unit test for reanchor (C15-3N) passed because it mocked `execute` with
`return_value` (not `side_effect`), so the file was never actually modified
before `_run_impl` reached the reanchor step.

---

## Fix

Three minimal changes in `local_model_executor.py`:

### 1. `_build_unified_diff_from_search_and_replacement`
Added `original_source_text: Optional[str] = None` parameter.
When provided, uses it as the source for anchor-line lookup instead of reading from disk.

### 2. `_reanchor_pipeline_patch_to_locked_search`
Added `original_source_text: Optional[str] = None` parameter.
When provided:
- Uses it as `current_text` for `locked_search in current_text` check
- Passes it through to `_build_unified_diff_from_search_and_replacement`

### 3. Callsite in `_run_impl`
Passes `original_source_text=original_target_content` — the snapshot
captured **before** `LocalHealPipelineCapabilityExecutor.execute` runs.

---

## Test Added

`test_pipeline_projection_reanchors_to_locked_search_when_current_source_modified_by_pipeline`

Uses `side_effect` (not `return_value`) to write the modified file content
during `execute`, accurately reproducing the real timing sequence.

---

## Live Evidence (2/2 runs)

| Field | Before (C15-3R) | After (C15-3S) |
|-------|-----------------|----------------|
| `pipeline_locked_search_reanchored` | `False` | **`True`** |
| `patch_lifecycle_state` | `isolation_attempted_apply_failed` | **`isolation_applied_hash_match_verifier_failed`** |
| `apply_failure_root_cause` | `search_block_mismatch_current_source` | **`""`** |
| `candidate_isolated` | `False` | **`True`** |
| `hash_match` | `False` | **`True`** |
| `retry_eligible` | `False` | **`True`** |
| `pipeline_retry_delegated` | `False` | **`True`** |
| `delegated_retry_status` | N/A | `EMPTY_RESPONSE` |

---

## Gate Progress

```
Gate A: locked_search present                     → PASS (was passing)
Gate B: reanchor activated                        → PASS (was FAIL → now fixed)
Gate C: candidate_isolated + hash_match           → PASS (now reachable)
Gate D: retry_eligible + pipeline_retry_delegated → PASS (now reachable)
Gate E: delegated_retry response quality          → FAIL → C15-3T
```

---

## Next Task: C15-3T

`delegated_retry_status: EMPTY_RESPONSE`
`delegated_retry_failure_reason: EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE`
`semantic_retry_prompt_len: 0`
`semantic_retry_client_class: ""`

The delegated retry is now being invoked, but the provider returns an empty
response. C15-3T should diagnose why the retry prompt is not being built
or delivered to the model.

**Boundary**: Do not change CapabilityPlanner, HybridRouteDecision, verifier,
parser, or candidate isolation. No new routes. No hardcoded toy logic. No
`solved=True` claim without empirical verifier pass.
