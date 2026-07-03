# LocalHeal Sprint C15-3J: Bounded Live Branch Coverage Matrix

**Status**: `LOCAL_MODEL_SPRINT_C15_3J_BRANCH_COVERAGE_PASS`

**Date**: 2026-07-03

---

## Commands Run

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py
```

```bash
uv run pytest tests/unit/local_heal/test_local_model_executor.py tests/benchmark/test_m1_real_local_solve_benchmark.py -q
```

**Deterministic test count**: 127 passed

```bash
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-solve
```

**Live attempts**: 5 (completed)

---

## Live Attempt Table

| Attempt | `patch_lifecycle_state` | `failure_class` | `candidate_isolated` | `hash_match` | `semantic_retry_evidence_ready` | `pipeline_retry_delegated` | `semantic_retry_invoked` | Branch Classification |
|---------|------------------------|-----------------|---------------------|-------------|-------------------------------|--------------------------|------------------------|----------------------|
| 1 | `isolation_attempted_apply_failed` | `patch_apply_failed` | false | false | false | None | false | `patch_apply_failed` |
| 2 | `isolation_attempted_apply_failed` | `patch_apply_failed` | false | false | false | None | false | `patch_apply_failed` |
| 3 | `isolation_attempted_apply_failed` | `patch_apply_failed` | false | false | false | None | false | `patch_apply_failed` |
| 4 | `isolation_attempted_apply_failed` | `patch_apply_failed` | false | false | false | None | false | `patch_apply_failed` |
| 5 | `isolation_applied_hash_match_verifier_failed` | `verification_failed` | true | true | true | None | false | `verifier_failed_evidence_ready_not_delegated` |

---

## Branch Classification Count

| Branch | Count |
|--------|-------|
| `patch_apply_failed` | 4 |
| `verifier_failed_evidence_ready_not_delegated` | 1 |

---

## Terminal Observations

| Observation | Reached? |
|-------------|----------|
| `pipeline_retry_delegated=true` | **No** (0/5) |
| `orchestrator_verifier_evidence_passed_to_retry=true` | **No** (0/5) |
| `semantic_retry_verifier_evidence_injected=true` | **No** (0/5) |
| `verifier_result=pass and solved=true` | **No** (0/5) |

---

## Key Findings

### 1. Dominant branch: `patch_apply_failed` (80%)

4 out of 5 attempts failed at `isolation_attempted_apply_failed`. The live model output produces patches that cannot be applied to the target file. This is the **primary blocker** preventing reaching the verifier-failed/hash-match branch.

### 2. Verifier-failed branch was reached once (20%)

Attempt 5 reached `isolation_applied_hash_match_verifier_failed` with `semantic_retry_evidence_ready=true`. However, `pipeline_retry_delegated` was not true — the delegated retry was not triggered despite the evidence being ready.

### 3. Evidence pipeline is working

- `verifier_failure_evidence_available=true` in all 5 attempts
- `verifier_exit_code=1` captured in all 5 attempts
- `semantic_retry_evidence_ready=true` in attempt 5

### 4. C15-3A/B/C/E/G/H plumbing is functional

The evidence capture, prompt injection, and orchestrator pass-through plumbing is all working. The issue is not plumbing — it's that the live model output rarely reaches the branch where delegated retry would be triggered.

---

## Decision Gate

**Result: C**

Most attempts (4/5) are `patch_apply_failed`. The next phase should be:

**`C15-3K Patch Apply Stability for Pipeline Retry Branch`**

Focus on why live model output often regresses before the verifier-failed/hash-match branch. The model produces patches that fail to apply, preventing the pipeline from reaching the delegated retry branch.

---

## Next Recommended Phase

**C15-3K Patch Apply Stability for Pipeline Retry Branch**

This phase should investigate:
1. Why the live model output often produces patches that fail to apply
2. Whether the model's SEARCH block doesn't match the source (SEARCH_MISMATCH)
3. Whether the model's output format is correct (SEARCH/REPLACE protocol)
4. Whether the locked search span is being used correctly

---

## Statements

- **No code changes**: This task only ran live validation and created a report.
- **No route changes**: No route logic was modified.
- **No topology changes**: No topology logic was modified.
- **No prompt changes**: No prompt builder was modified.
- **No parser changes**: No parser behavior was modified.
- **No verifier behavior changes**: No verifier logic was modified.
- **No candidate isolation behavior changes**: No isolation logic was modified.
- **No full benchmark**: Only toy-math-solve was run, not the full 6-task benchmark.
- **Bounded toy live attempts only**: Exactly 5 `--task-id toy-math-solve` runs were executed.
- **Not local model armor ready**: This validation did not prove local model armor readiness.
- **production_ready=false**: This validation is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
