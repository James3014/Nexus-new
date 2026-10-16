# LocalHeal Sprint C15-3N: Pipeline Reanchor and Live Branch Shift

**Status**: `LOCAL_MODEL_SPRINT_C15_3N_REANCHOR_AND_LIVE_SHIFT_PASS`

**Date**: 2026-07-03

---

## Summary

Extended the `localheal_pipeline` projected-diff path so it can rebuild a target-only unified diff from `locked_search` when the pipeline patch preimage does not match the current source.

Deterministic coverage proves the reanchor path.

A bounded live rerun on `toy-math-solve` no longer landed on `patch_apply_failed`. The latest live attempt advanced to:

- `patch_lifecycle_state = isolation_applied_hash_match_verifier_failed`
- `failure_class = verification_failed`
- `candidate_isolated = true`
- `hash_match = true`
- `retry_eligible = true`
- `pipeline_retry_delegated = true`

This is a real downstream branch shift beyond C15-3L's `patch_apply_failed_with_reason` plateau.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Added pipeline projected-diff reanchor to `locked_search` and shared unified diff builder |
| `tests/unit/local_heal/test_local_model_executor.py` | Added deterministic coverage proving projected diff reanchor before isolated apply |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/local_model_executor.py \
  tests/unit/local_heal/test_local_model_executor.py
```

```bash
uv run pytest tests/unit/local_heal/test_local_model_executor.py -q
```

**Deterministic result**: `138 passed in 1.78s`

```bash
uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

**Live result**: one bounded attempt completed in `46.5s`

---

## Deterministic Reanchor Proof

Added focused test coverage proving:

1. pipeline final patch can arrive with a mismatched preimage
2. `locked_search` still matches the current target source
3. executor rebuilds the diff before isolated apply
4. isolated apply receives the rebuilt diff and matching candidate hash

---

## Live Branch Shift

Latest bounded live run fields:

| Field | Value |
|------|-------|
| `patch_lifecycle_state` | `isolation_applied_hash_match_verifier_failed` |
| `failure_class` | `verification_failed` |
| `candidate_isolated` | `true` |
| `hash_match` | `true` |
| `isolated_apply_status` | `applied` |
| `retry_eligible` | `true` |
| `pipeline_retry_delegated` | `true` |
| `delegated_retry_failure_reason` | `EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE` |

Important note:

- In this specific live attempt, `protocol_normalization.pipeline_locked_search_reanchored = false`.
- That means the deterministic reanchor branch is present and tested, but this single live sample advanced because the emitted patch preimage already matched the current source.
- Therefore the live run proves the branch plateau has moved, but does **not** by itself prove the reanchor branch was the mechanism used on this exact attempt.

---

## Decision Gate

**Result: branch shift confirmed**

The C15 line is no longer dominated by `patch_apply_failed_with_reason` in the latest bounded live attempt.

The next narrow phase should focus on verifier-failed semantic quality / delegated retry closure, not patch apply root cause.

Recommended next phase:

**`C15-3O Verifier-Failed Semantic Retry Closure`**

Focus:

1. inspect why delegated retry ended at `EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE`
2. verify whether verifier-failed evidence is sufficient but retry prompt/model output is still weak
3. keep route/topology unchanged
4. do not claim solved unless verifier passes

---

## Statements

- **No route changes**: No route logic changed.
- **No topology changes**: No topology selector changed.
- **No prompt changes**: No prompt wording changed.
- **No parser changes**: No parser contract changed.
- **No verifier behavior changes**: Verifier remained authoritative.
- **No candidate isolation behavior changes**: Isolated apply/verifier implementations unchanged.
- **No public claim**: `public_claim_allowed=false`
- **Not solved**: `toy-math-solve` still failed verifier.
- **Not local model armor ready**
- **production_ready=false**
