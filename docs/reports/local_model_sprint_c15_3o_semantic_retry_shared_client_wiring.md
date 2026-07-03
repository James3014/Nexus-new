# LocalHeal Sprint C15-3O: Semantic Retry Shared-Client Wiring

**Status**: `LOCAL_MODEL_SPRINT_C15_3O_SHARED_CLIENT_WIRING_PASS_WITH_LIVE_VARIANCE`

**Date**: 2026-07-03

---

## Summary

Aligned semantic retry model invocation with the main patch-synthesis provider path.

Before this change, `local_model_executor` delegated verifier-failed retry through `HealPipeline`, but `HealOrchestrator._attempt_semantic_retry()` instantiated `OllamaLLMClient(None)` directly instead of reusing the patch phase client/provider already attached to the pipeline.

After this change:

- semantic retry prefers the same `patch_phase.llm_client` used by patch synthesis
- focused tests prove semantic retry reuses the shared client

This keeps semantic retry on the same provider path as the rest of the local-heal execution line.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/orchestrator.py` | Added semantic-retry client resolution that reuses `patch_phase.llm_client` when available |
| `tests/unit/local_heal/test_local_model_executor.py` | Added focused tests for shared-client resolution and semantic retry client reuse |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/orchestrator.py \
  tests/unit/local_heal/test_local_model_executor.py
```

```bash
uv run pytest tests/unit/local_heal/test_local_model_executor.py -q
```

**Deterministic result**: `140 passed in 1.76s`

```bash
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

**Live result**: one bounded attempt completed in `56.79s`

---

## Deterministic Proof

Focused tests now prove:

1. orchestrator semantic retry resolves the shared patch-phase client when present
2. `_attempt_semantic_retry()` uses that shared client instead of opening a separate fallback client path
3. verifier evidence metadata still records on the retry path

---

## Live Outcome

The bounded live rerun did **not** re-hit the verifier-failed delegated-retry branch.

Instead it regressed earlier to:

| Field | Value |
|------|-------|
| `patch_lifecycle_state` | `isolation_attempted_apply_failed` |
| `failure_class` | `patch_apply_failed` |
| `apply_failure_root_cause` | `search_block_mismatch_current_source` |
| `retry_eligible` | `false` |
| `pipeline_retry_delegated` | `false` |

This means the live sample cannot confirm or deny whether the shared-client wiring removes the previous `EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE` delegated-retry outcome, because the run never reached that branch.

---

## Decision Gate

**Result: deterministic wiring fixed, live branch proof still pending**

What is now proven:

- semantic retry no longer has to fork to a separate direct client path in deterministic coverage

What is not yet proven:

- a live verifier-failed delegated-retry run after this wiring change that no longer ends in `EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE`

Next narrow phase:

**`C15-3P Verifier-Eligible Branch Stability`**

Focus:

1. improve stability of reaching `isolation_applied_hash_match_verifier_failed`
2. keep route/topology/prompt contracts unchanged
3. once that branch is re-hit live, re-check delegated retry outcome and evidence flags

---

## Statements

- **No route changes**
- **No topology changes**
- **No prompt wording changes**
- **No parser changes**
- **No verifier behavior changes**
- **No candidate isolation behavior changes**
- **Not solved**
- **Not local model armor ready**
- **production_ready=false**
- **public_claim_allowed=false**
