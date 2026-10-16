# LocalHeal Sprint C15-3D: Bounded Live Toy Validation

**Status**: `LOCAL_MODEL_SPRINT_C15_3D_LIVE_TOY_VALIDATION_BLOCKED`

**Date**: 2026-07-03

---

## Commands Run

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py
```

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

**Exit status**: 0 (completed)

---

## Live Result Classification

**`evidence_captured_not_ready`**

Reason: Verifier failed (`verifier_result=fail`) but verifier evidence was NOT captured because stdout/stderr/error are all empty. The verifier command ran but produced no output, so `verifier_failure_evidence_available=false`.

---

## Key Row Fields

| Field | Value |
|-------|-------|
| `task_id` | toy-math-solve |
| `execution_topology` | localheal_pipeline |
| `route_truth_source` | CapabilityPlanner |
| `phase_reached` | verification |
| `pipeline_failure_reason` | SEARCH_MISMATCH:SEARCH_MISMATCH |
| `patch_synthesis_output_len` | 163 |
| `pipeline_final_patch_len` | 152 |
| `patch_lifecycle_state` | `isolation_applied_hash_match_verifier_failed` |
| `failure_class` | `search_mismatch` |
| `unknown_reason` | (empty) |
| `verifier_failure_evidence_available` | **false** |
| `verifier_failure_kind` | unknown_verifier_failure |
| `verifier_stdout_excerpt` | (empty) |
| `verifier_stderr_excerpt` | (empty) |
| `verifier_exit_code` | (empty) |
| `verifier_command_hash` | 3db1e85eb525a5fe |
| `semantic_retry_evidence_ready` | **false** |
| `semantic_retry_verifier_evidence_injected` | false |
| `semantic_retry_verifier_evidence_fields` | (empty) |
| `semantic_retry_prompt_evidence_hash` | (empty) |
| `orchestrator_verifier_evidence_passed_to_retry` | false |
| `orchestrator_verifier_evidence_fields` | (empty) |
| `orchestrator_retry_prompt_evidence_hash` | (empty) |
| `protocol_retry_attempted` | true |
| `protocol_retry_count` | 2 |
| `semantic_retry_invoked` | **false** |
| `semantic_retry_count` | 0 |
| `same_span_retry` | false |
| `candidate_isolation_attempted` | (missing from row) |
| `candidate_isolated` | true |
| `isolated_apply_status` | (missing from row) |
| `isolated_apply_error` | (missing from row) |
| `selected_candidate_hash` | 0e4e2e95... |
| `applied_patch_hash` | 0e4e2e95... |
| `hash_match` | true |
| `verifier_result` | fail |
| `solved` | false |

---

## C15 Evidence Path Analysis

### C15-1 patch_lifecycle_state: WORKING
- `isolation_applied_hash_match_verifier_failed` — correctly identifies that patch was applied, hashes match, but verifier failed.

### C15-2 failure_class: WORKING
- `search_mismatch` — correctly classifies the failure from `pipeline_failure_reason`.

### C15-3A verifier failure evidence: NOT TRIGGERED
- `verifier_failure_evidence_available=false` because verifier produced no stdout/stderr/error.
- Root cause: The verifier command (`python3 -c "print(1)"`) ran and returned exit code 1 (fail), but `stdout_tail` and `stderr_tail` are empty in the receipt. This means the verifier output was not captured or was cleared.

### C15-3B prompt injection: NOT ACTIVATED
- `semantic_retry_verifier_evidence_injected=false` — expected, since C15-3A evidence was not available.

### C15-3C orchestrator pass-through: NOT TRIGGERED
- `orchestrator_verifier_evidence_passed_to_retry=false` — expected, since evidence was not available.
- `semantic_retry_invoked=false` — semantic retry was not invoked because `semantic_retry_evidence_ready=false`.

---

## Current Blocker

**Verifier evidence capture gap**: The verifier command runs and fails (exit code 1), but `stdout_tail` and `stderr_tail` in the `IsolatedVerifierReceipt` are empty. This means `compute_verifier_failure_evidence` sees no evidence and sets `verifier_failure_evidence_available=false`.

This is NOT a code bug in C15-3A — the function correctly handles empty evidence. The issue is that the verifier receipt doesn't contain stdout/stderr, likely because:
1. The verifier command output is not being captured, OR
2. The verifier receipt fields are being cleared before reaching the evidence capture point.

---

## Next Recommended Phase

**C15-3E: Verifier Receipt Stdout/Stderr Capture Fix**

This phase should investigate why the `IsolatedVerifierReceipt` has empty `stdout_tail` and `stderr_tail` when the verifier fails. The fix should ensure verifier output is captured in the receipt so C15-3A evidence capture can work.

---

## Statements

- **No code changes**: This task only ran live validation and created a report.
- **No route changes**: No route logic was modified.
- **No prompt changes**: No prompt builder was modified.
- **No parser changes**: No parser behavior was modified.
- **No verifier behavior changes**: No verifier logic was modified.
- **No candidate isolation behavior changes**: No isolation logic was modified.
- **One bounded live run only**: Exactly one `--task-id toy-math-solve` run was executed.
- **Not local model armor ready**: This validation did not prove local model armor readiness.
- **production_ready=false**: This validation is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
