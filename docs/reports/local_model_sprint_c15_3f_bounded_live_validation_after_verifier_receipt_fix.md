# LocalHeal Sprint C15-3F: Bounded Live Validation After Verifier Receipt Fix

**Status**: `verifier_evidence_captured_not_retry_ready`

**Date**: 2026-07-03

---

## Summary

Ran exactly one bounded live `toy-math-solve` validation after C15-3E.

The verifier receipt path is now partially active:

- `verifier_receipt_exit_code_present=true`
- `verifier_exit_code=1`
- `patch_lifecycle_state=isolation_applied_hash_match_verifier_failed`
- `candidate_isolated=true`
- `hash_match=true`

But verifier failure evidence is still not retry-ready:

- `verifier_stdout_tail_present=false`
- `verifier_stderr_tail_present=false`
- `verifier_error_present=false`
- `verifier_failure_evidence_available=false`
- `semantic_retry_evidence_ready=false`
- `orchestrator_verifier_evidence_passed_to_retry=false`
- `semantic_retry_verifier_evidence_injected=false`

Classification: `verifier_evidence_captured_not_retry_ready`

---

## Commands Run

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py
```

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

---

## Latest Toy Row

Source:
`.nexus/reports/local_model/m1_real_local_solve_results.jsonl`

| Field | Value |
|------|-------|
| `task_id` | `toy-math-solve` |
| `execution_topology` | `localheal_pipeline` |
| `route_truth_source` | `CapabilityPlanner` |
| `phase_reached` | `verification` |
| `pipeline_failure_reason` | `NO_BLOCKS_FOUND:NO_BLOCKS_FOUND` |
| `patch_synthesis_output_len` | `86` |
| `pipeline_final_patch_len` | `154` |
| `patch_lifecycle_state` | `isolation_applied_hash_match_verifier_failed` |
| `failure_class` | `no_blocks_found` |
| `unknown_reason` | `` |
| `verifier_stdout_tail_present` | `false` |
| `verifier_stderr_tail_present` | `false` |
| `verifier_error_present` | `false` |
| `verifier_receipt_exit_code_present` | `true` |
| `verifier_failure_evidence_available` | `false` |
| `verifier_failure_kind` | `nonzero_exit` |
| `verifier_stdout_excerpt` | `` |
| `verifier_stderr_excerpt` | `` |
| `verifier_exit_code` | `1` |
| `verifier_command_hash` | `0a7705128a9c79de` |
| `semantic_retry_evidence_ready` | `false` |
| `semantic_retry_verifier_evidence_injected` | `false` |
| `semantic_retry_verifier_evidence_fields` | `` |
| `semantic_retry_prompt_evidence_hash` | `` |
| `orchestrator_verifier_evidence_passed_to_retry` | `false` |
| `orchestrator_verifier_evidence_fields` | `` |
| `orchestrator_retry_prompt_evidence_hash` | `` |
| `protocol_retry_attempted` | `true` |
| `protocol_retry_count` | `2` |
| `semantic_retry_invoked` | `false` |
| `semantic_retry_count` | `0` |
| `same_span_retry` | `false` |
| `candidate_isolation_attempted` | `true` |
| `candidate_isolated` | `true` |
| `isolated_apply_status` | `applied` |
| `isolated_apply_error` | `` |
| `selected_candidate_hash` | `331d66eca27ab63871e0c4cc0745502bb2fae7a6852dd21c98ad9ad742c2a02e` |
| `applied_patch_hash` | `331d66eca27ab63871e0c4cc0745502bb2fae7a6852dd21c98ad9ad742c2a02e` |
| `hash_match` | `true` |
| `verifier_result` | `fail` |
| `solved` | `false` |

---

## Decision Rule Applied

Matched rule:

```text
verifier receipt presence fields are true
AND verifier_failure_evidence_available=false
=> verifier_evidence_captured_not_retry_ready
```

Why:

- Receipt capture is no longer completely absent because `verifier_receipt_exit_code_present=true`.
- Retry evidence is still not usable because no stdout/stderr/error payload is present.

---

## Interpretation

What is now proven:

1. The run reached real isolated apply and real verifier execution.
2. The candidate patch was applied in isolation.
3. Hash match was proven.
4. The verifier receipt fix partially worked because exit code is now preserved.

What is not yet proven:

1. Verifier stdout/stderr/error text is reaching downstream metadata.
2. `compute_verifier_failure_evidence()` can mark evidence available.
3. Semantic retry can become evidence-ready.
4. Orchestrator can pass verifier evidence into retry.
5. Retry prompt evidence injection can occur.

---

## Residual Blocker

Current blocker is no longer route truth, patch projection, or candidate isolation.

Current blocker:

```text
verifier failed after isolated apply succeeded,
but verifier receipt still carries only exit_code without bounded stdout/stderr/error evidence.
```

Because `compute_verifier_failure_evidence()` requires `stdout_excerpt or stderr_excerpt or verifier_error`,
an exit code alone is not enough to mark:

- `verifier_failure_evidence_available=true`
- `semantic_retry_evidence_ready=true`

---

## Statements

- **Validation only**: This task performed bounded live validation only.
- **No source changes**: No runtime code changes were made in C15-3F.
- **No new route**: No RouteMode, Router, Planner, or topology selector added.
- **No CapabilityPlanner changes**: Planner remained the only route truth source.
- **No HybridRouteDecision changes**: Route contract unchanged.
- **No retry loop changes**: No new retry loop created.
- **No parser changes**: Protocol behavior unchanged.
- **No verifier behavior changes**: Verifier execution remained read-only evidence.
- **No candidate isolation changes**: Isolation semantics unchanged.
- **No patch lifecycle changes**: Patch lifecycle contract unchanged.
- **No failure classifier changes**: Failure classifier unchanged.
- **No prompt tuning**: Prompt wording unchanged.
- **Not toy-math-solve solved**: `verifier_result=fail`, `solved=false`.
- **Not local model armor ready**: Evidence path is still incomplete.
- **production_ready=false**
- **public_claim_allowed=false**
