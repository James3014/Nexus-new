# LocalHeal Sprint C15-4C-2: Forced Delegated Retry Live Probe

**Status**: `C15_4C_2_DELEGATED_RETRY_SOLVED_NOT_PROVEN`

**Date**: 2026-07-03

---

## Commands Run

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py tests/benchmark/test_m1_real_local_solve_benchmark.py
```

```bash
uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -k "c15_4c_1 or m1_real_local_solve" -q
```

**Test count**: 19 passed

```bash
export NEXUS_BENCHMARK_APPEND=1
timeout 180 /Users/jameschen/.local/bin/uv run python scripts/bench/m1_real_local_solve_benchmark.py --task-id toy-math-verifier-evidence-gap
```

**Live attempts**: 3 completed

---

## Live Attempt Table

| Attempt | `verifier_result` | `solved` | `solve_mechanism` | `pipeline_retry_delegated` | `delegated_retry_stage` | `delegated_retry_status` | `semantic_retry_prompt_has_verifier_evidence` |
|---------|------------------|---------|-------------------|--------------------------|------------------------|------------------------|----------------------------------------------|
| 1 | fail | false | delegated_retry_unresolved | **true** | first_patch_failed | REPLACE_SYNTAX_ERROR | **true** |
| 2 | fail | false | delegated_retry_unresolved | **true** | first_patch_failed | REPLACE_SYNTAX_ERROR | **true** |
| 3 | fail | false | delegated_retry_unresolved | **true** | first_patch_parser_rejected | SEARCH_MISMATCH | **true** |

---

## Latest JSONL Fields (Attempt 3)

| Field | Value |
|-------|-------|
| `task_id` | toy-math-verifier-evidence-gap |
| `verifier_result` | fail |
| `solved` | false |
| `solve_mechanism` | delegated_retry_unresolved |
| `patch_lifecycle_state` | isolation_applied_hash_match_verifier_failed |
| `failure_class` | verification_failed |
| `semantic_retry_invoked` | true |
| `semantic_retry_prompt_has_verifier_evidence` | **true** |
| `pipeline_retry_delegated` | **true** |
| `delegated_retry_stage` | first_patch_parser_rejected |
| `delegated_retry_status` | SEARCH_MISMATCH |
| `delegated_retry_provider_called` | true |
| `retry_not_invoked_reason` | none |
| `verifier_stdout_excerpt` | EVIDENCE: normalize_score does not clamp output to [0, 1] range... |

---

## Solve Mechanism Classification

| Attempt | Classification |
|---------|---------------|
| 1 | `delegated_retry_unresolved` — delegated retry invoked, verifier evidence injected, but REPLACE_SYNTAX_ERROR |
| 2 | `delegated_retry_unresolved` — delegated retry invoked, verifier evidence injected, but REPLACE_SYNTAX_ERROR |
| 3 | `delegated_retry_unresolved` — delegated retry invoked, verifier evidence injected, but SEARCH_MISMATCH |

---

## Verifier Evidence Capture Verification

| Field | Attempt 1 | Attempt 2 | Attempt 3 |
|-------|-----------|-----------|-----------|
| `verifier_failure_evidence_available` | true | true | true |
| `semantic_retry_evidence_ready` | true | true | true |
| `semantic_retry_prompt_has_verifier_evidence` | **true** | **true** | **true** |
| `orchestrator_verifier_evidence_passed_to_retry` | **true** | **true** | **true** |
| `verifier_stdout_excerpt` | EVIDENCE: ... | EVIDENCE: ... | EVIDENCE: ... |

**Result**: Verifier evidence IS being captured and injected into the retry prompt.

---

## Delegated Retry Invocation Verification

| Field | Attempt 1 | Attempt 2 | Attempt 3 |
|-------|-----------|-----------|-----------|
| `pipeline_retry_delegated` | **true** | **true** | **true** |
| `delegated_retry_stage` | first_patch_failed | first_patch_failed | first_patch_parser_rejected |
| `delegated_retry_provider_called` | true | true | true |
| `retry_not_invoked_reason` | none | none | none |

**Result**: Delegated retry IS being invoked when conditions are met.

---

## Acceptance Criteria Check

| Criterion | Status |
|-----------|--------|
| `task_id=toy-math-verifier-evidence-gap` | ✅ All 3 attempts |
| `pipeline_retry_delegated=true` | ✅ All 3 attempts |
| `delegated_retry_stage indicates delegated retry path` | ✅ first_patch_failed / first_patch_parser_rejected |
| `delegated_retry_status=SUCCESS or equivalent` | ❌ All 3 failed (REPLACE_SYNTAX_ERROR / SEARCH_MISMATCH) |
| `verifier_result=pass` | ❌ All 3 failed |
| `solved=true` | ❌ All 3 failed |
| `solve_mechanism=delegated_retry` | ❌ solve_mechanism=delegated_retry_unresolved |
| `primary first-pass did not solve` | ✅ First pass failed |
| `pipeline_semantic_retry did not preempt delegated retry` | ✅ Delegated retry was invoked |

**Overall**: 4/9 criteria met. **delegated_retry solved = NOT_PROVEN**

---

## Residual Blocker

Delegated retry IS being invoked and verifier evidence IS being injected. The blocker is:

**The model produces patches that fail at the parser/apply stage during delegated retry.**

- Attempt 1-2: REPLACE_SYNTAX_ERROR (indentation issue after `if` statement)
- Attempt 3: SEARCH_MISMATCH (SEARCH block doesn't match source)

This is a **model output quality issue**, not a plumbing issue. The evidence pipeline is working correctly.

---

## Statements

- **No runtime behavior changed**: This task only ran live probes and created a report.
- **No benchmark behavior changed**: No benchmark code was modified.
- **No route authority changed**: No new RouteMode, Router, Planner, or topology selector.
- **production_ready=false**: This live probe is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.

---

## Next Recommended Task

**C15-4D Delegated Retry Output Quality Hardening**

The evidence pipeline is proven to work. The next step is to improve the delegated retry output quality so the model produces valid SEARCH/REPLACE patches during delegated retry. This may involve:
1. Improving the retry prompt to be more specific about SEARCH/REPLACE format
2. Adding retry-specific prompt instructions for the delegated retry path
3. Or accepting that delegated retry with current model quality may not solve

Alternatively, if delegated retry output quality cannot be improved without prompt changes, the next task could be:
**C15-4E Delegated Retry Claim Boundary Definition** — formally define what can and cannot be claimed about delegated retry.
