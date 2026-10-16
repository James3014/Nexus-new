# LocalHeal Sprint C15-3G: Exit-Code-Only Verifier Evidence Readiness

**Status**: `verifier_evidence_ready_not_passed_to_retry`

**Date**: 2026-07-03

---

## Summary

Advanced the verifier evidence path for bounded local-heal runs without changing route authority, planner behavior, verifier behavior, or adding a new retry loop.

Two downstream truth fixes were applied:

1. `compute_verifier_failure_evidence()` now treats `exit_code != 0` as bounded verifier failure evidence even when stdout/stderr/error are empty.
2. `compute_failure_class()` now lets terminal patch lifecycle states override earlier protocol-stage failure reasons once a real candidate has already been projected and verified in isolation.

Result:

- Previous live state: `verifier_evidence_captured_not_retry_ready`
- New live state: `verifier_evidence_ready_not_passed_to_retry`

---

## Files Changed

| File | Change |
|------|--------|
| `nexus/services/local_heal/local_model_executor.py` | Treat nonzero verifier exit code as evidence-ready input; prefer terminal verifier-failed lifecycle over stale protocol failure reason |
| `tests/unit/local_heal/test_local_model_executor.py` | Added and updated focused tests for exit-code-only evidence and lifecycle-overrides-reason classification |

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

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

**Focused test result**: `110 passed in 1.63s`

---

## Latest Live Row

Source:
`.nexus/reports/local_model/m1_real_local_solve_results.jsonl`

| Field | Value |
|------|-------|
| `task_id` | `toy-math-solve` |
| `execution_topology` | `localheal_pipeline` |
| `route_truth_source` | `CapabilityPlanner` |
| `phase_reached` | `verification` |
| `pipeline_failure_reason` | `NO_BLOCKS_FOUND:FILE_NOT_FOUND:UNKNOWN_PENDING` |
| `patch_synthesis_output_len` | `937` |
| `pipeline_final_patch_len` | `314` |
| `patch_lifecycle_state` | `isolation_applied_hash_match_verifier_failed` |
| `failure_class` | `verification_failed` |
| `unknown_reason` | `` |
| `verifier_stdout_tail_present` | `false` |
| `verifier_stderr_tail_present` | `false` |
| `verifier_error_present` | `false` |
| `verifier_receipt_exit_code_present` | `true` |
| `verifier_failure_evidence_available` | `true` |
| `verifier_failure_kind` | `nonzero_exit` |
| `verifier_stdout_excerpt` | `` |
| `verifier_stderr_excerpt` | `` |
| `verifier_exit_code` | `1` |
| `verifier_command_hash` | `8e569ab6cbe9fb6d` |
| `semantic_retry_evidence_ready` | `true` |
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
| `selected_candidate_hash` | `d9450db71ba57be736498ecf62ae48f09d5c1f241e99ba9a972760aba5d8c9eb` |
| `applied_patch_hash` | `d9450db71ba57be736498ecf62ae48f09d5c1f241e99ba9a972760aba5d8c9eb` |
| `hash_match` | `true` |
| `verifier_result` | `fail` |
| `solved` | `false` |

---

## What Improved

### 1. Failure class now matches actual terminal state

Before this change, a run could reach:

```text
patch_lifecycle_state = isolation_applied_hash_match_verifier_failed
```

while still being labeled:

```text
failure_class = no_blocks_found
```

Now the row truth is aligned:

```text
patch_lifecycle_state = isolation_applied_hash_match_verifier_failed
failure_class = verification_failed
```

### 2. Exit-code-only verifier fail now becomes evidence-ready

Before this change:

```text
verifier_receipt_exit_code_present = true
verifier_failure_evidence_available = false
semantic_retry_evidence_ready = false
```

After this change:

```text
verifier_receipt_exit_code_present = true
verifier_failure_evidence_available = true
semantic_retry_evidence_ready = true
```

No synthetic stdout/stderr was invented. The row still truthfully records empty excerpts.

---

## Classification

This live result matches:

```text
verifier_evidence_ready_not_passed_to_retry
```

Reason:

- `verifier_failure_evidence_available=true`
- `semantic_retry_evidence_ready=true`
- `orchestrator_verifier_evidence_passed_to_retry=false`

---

## Interpretation

What is now proven:

1. The model produced a real candidate patch.
2. The candidate patch was projected to the target file.
3. Isolated apply succeeded.
4. Applied hash matched selected candidate hash.
5. The isolated verifier failed.
6. Exit-code-only verifier failure is now treated as bounded evidence.
7. Retry readiness now reflects the true downstream state.

What remains unproven:

1. Orchestrator pass-through of verifier evidence for this live path.
2. Prompt evidence injection for this live path.
3. A semantic retry actually running from this evidence path.
4. A verifier-passing repaired patch.

---

## Residual Blocker

Current blocker is no longer evidence readiness.

Current blocker:

```text
the downstream isolated-verifier failure path can now classify evidence as retry-ready,
but that path still does not feed a consumer that passes the evidence into an actual retry prompt.
```

This is why:

- `semantic_retry_evidence_ready=true`
- but `orchestrator_verifier_evidence_passed_to_retry=false`
- and `semantic_retry_invoked=false`

---

## Statements

- **No new route**: No RouteMode, Router, Planner, or topology selector added.
- **No CapabilityPlanner changes**: Planner remains the only route truth source.
- **No HybridRouteDecision changes**: Route contract unchanged.
- **No verifier behavior changes**: Verifier execution remains read-only evidence.
- **No candidate isolation changes**: Apply/hash/isolation semantics unchanged.
- **No patch lifecycle expansion**: Existing lifecycle states were reused.
- **No prompt tuning**: Prompt wording unchanged.
- **No synthetic verifier logs**: Empty stdout/stderr stayed empty.
- **No new retry loop**: This change only advanced readiness truth.
- **Not toy-math-solve solved**: `verifier_result=fail`, `solved=false`.
- **Not local model armor ready**
- **production_ready=false**
- **public_claim_allowed=false**
