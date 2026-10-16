# LocalHeal Sprint C15-3H: Delegated Retry Consumer Wiring

**Status**: `DETERMINISTIC_CONSUMER_WIRING_PASS_LIVE_BRANCH_NOT_REACHED`

**Date**: 2026-07-03

---

## Summary

Wired the existing delegated `pipeline.run()` consumer into the `localheal_pipeline` isolated-verifier path without adding a new route, topology, planner, or retry loop.

This slice does two things:

1. Preserves `semantic_retry_seed` when the legacy pipeline wrapper converts into V2 context.
2. Reuses the existing delegated retry pattern after isolated verifier failure, so retry-ready verifier evidence can be passed into pipeline/orchestrator on the next bounded attempt.

Deterministic tests prove the consumer wiring works.

The single bounded live rerun available in this slice did not exercise the target verifier-failed branch; it regressed earlier to `patch_apply_failed`, so live proof of `orchestrator_verifier_evidence_passed_to_retry=true` remains pending.

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/pipeline.py` | Promote `route_context.semantic_retry_seed` into V2 operational context |
| `nexus/services/local_heal/local_model_executor.py` | Reuse existing delegated pipeline retry after isolated verifier failure; merge orchestrator retry metadata back into raw_meta |
| `tests/unit/local_heal/test_local_model_executor.py` | Add focused tests for seed promotion and delegated consumer metadata |

---

## Commands Run

```bash
python3 -m py_compile \
  nexus/services/local_heal/pipeline.py \
  nexus/services/local_heal/local_model_executor.py \
  tests/unit/local_heal/test_local_model_executor.py
```

```bash
uv run pytest tests/unit/local_heal/test_local_model_executor.py -q
```

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

**Focused test result**: `112 passed in 1.50s`

---

## Deterministic Proof

### Seed promotion

`LegacyHealContext.to_v2()` now carries:

- `verifier_failure_evidence_available`
- `semantic_retry_evidence_ready`
- `failure_class`
- `verifier_failure_kind`
- `verifier_stdout_excerpt`
- `verifier_stderr_excerpt`
- `verifier_exit_code`
- `verifier_command_hash`

from:

```text
route_context["semantic_retry_seed"]
```

into the V2 operational context consumed by the orchestrator.

### Delegated consumer

When the isolated path reaches:

```text
candidate_isolated=true
hash_match=true
semantic_retry_evidence_ready=true
failure_class in {verification_failed, semantic_wrong_patch}
```

`local_model_executor.py` now reuses the existing delegated pipeline retry pattern and records:

- `retry_available`
- `pipeline_retry_delegated`
- `delegated_retry_failure_reason`
- `delegated_retry_final_patch_len`
- `delegated_retry_output_class`
- `delegated_retry_parser_error_kind`
- `delegated_retry_status`
- `delegated_retry_output_excerpt`
- `orchestrator_verifier_evidence_passed_to_retry`
- `orchestrator_verifier_evidence_fields`
- `orchestrator_retry_prompt_evidence_hash`
- `semantic_retry_verifier_evidence_injected`
- `semantic_retry_verifier_evidence_fields`
- `semantic_retry_prompt_evidence_hash`

back into the row metadata.

---

## Latest Live Row

The bounded live rerun did not stay on the verifier-failed/hash-match branch.

Observed row:

| Field | Value |
|------|-------|
| `phase_reached` | `verification` |
| `pipeline_failure_reason` | `LOGIC_REGRESSION:VERIFICATION_FAILED` |
| `pipeline_final_patch_len` | `213` |
| `patch_lifecycle_state` | `isolation_attempted_apply_failed` |
| `failure_class` | `patch_apply_failed` |
| `candidate_isolated` | `false` |
| `hash_match` | `false` |
| `semantic_retry_evidence_ready` | `false` |
| `retry_available` | `false` |
| `retry_not_invoked_reason` | `semantic_retry_evidence_not_ready` |
| `pipeline_retry_delegated` | `false` |

Interpretation:

- The new consumer wiring was not exercised on this run.
- The model drifted to an earlier blocker (`patch_apply_failed`) before the new consumer gate could activate.

---

## Residual Blocker

Current remaining proof gap:

```text
We have deterministic proof that the delegated consumer wiring works,
but the available live rerun in this slice did not reach the verifier-failed/hash-match branch needed to exercise it.
```

This is a live-state coverage problem, not a focused-test failure.

---

## Statements

- **No new route**: No RouteMode, Router, Planner, or topology selector added.
- **No CapabilityPlanner changes**: Planner remains the only route truth source.
- **No HybridRouteDecision changes**: Route contract unchanged.
- **No new retry loop**: Reused the existing delegated pipeline retry pattern.
- **No verifier behavior changes**: Verifier remains read-only evidence.
- **No parser changes**: Parser/protocol behavior unchanged.
- **No candidate isolation changes**: Isolation semantics unchanged.
- **No synthetic verifier logs**: Empty stdout/stderr stayed empty.
- **Deterministic proof only for this slice**: Live branch coverage is still incomplete.
- **Not toy-math-solve solved**
- **Not local model armor ready**
- **production_ready=false**
- **public_claim_allowed=false**
