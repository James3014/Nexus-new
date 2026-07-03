# LocalHeal Sprint C15-4E: Delegated Retry Claim Boundary and Next-Path Decision

**Status**: `C15_4E_DELEGATED_RETRY_CLAIM_BOUNDARY_PASS`

**Date**: 2026-07-04

**Base commit**: `87c25e34c docs: record delegated retry bounded live recheck`

---

## Evidence Reviewed

| Report | Key Finding |
|--------|-------------|
| C15-4C-2 | Delegated retry invoked 3/3 attempts, verifier evidence injected 3/3, but 0/3 solved |
| C15-4D-0 | Delegated retry fully reuses C11/C13 SEARCH/REPLACE protocol contract (`CONTRACT_REUSED`) |
| C15-4D-1 | Failure taxonomy: 2/3 INDENTATION_SYNTAX_ERROR, 1/3 SEARCH_NOT_EXACT_SOURCE |
| C15-4D-2A | Prompt ordering guard RED confirmed (verifier before locked SEARCH) |
| C15-4D-2B | Prompt reordering applied; all 5 guard tests GREEN |
| C15-4D-3 | Live recheck: same REPLACE_SYNTAX_ERROR. Prompt ordering did NOT improve quality. Cumulative: 3/4 INDENTATION_SYNTAX_ERROR |

---

## Claim Boundary

### Allowed Internal Claims

1. **Delegated retry branch is wired** — `pipeline_retry_delegated=true` confirmed across 4 attempts.
2. **Delegated retry eligibility gate works** — semantic_retry_evidence_ready, failure_class, candidate_isolation checks all pass.
3. **Verifier evidence is passed into retry** — `semantic_retry_prompt_has_verifier_evidence=true`, `orchestrator_verifier_evidence_passed_to_retry=true` confirmed.
4. **C11/C13 SEARCH/REPLACE contract is reused** — system prompt (`build_patch_system_prompt`) is identical for primary and delegated retry.
5. **Candidate isolation and verifier receipt can expose failure** — patch_lifecycle_state, failure_class, delegated_retry_status all project correctly into JSONL.
6. **Current bounded task shows model output quality blocker** — 3/4 INDENTATION_SYNTAX_ERROR on `toy-math-verifier-evidence-gap` with 7B model.

### Forbidden Claims

- delegated_retry solved
- local armor ready
- production ready
- 7B can reliably repair verification failures
- public claim allowed
- model quality fixed
- prompt ordering solved delegated retry
- delegated retry output quality is acceptable

### Conditions Required to Upgrade Claim Status

| Current Status | Upgrade Path | Required Evidence |
|---------------|-------------|-------------------|
| delegated_retry solved NOT_PROVEN | → PROVEN | At least 1 bounded run with `verifier_result=pass`, `solved=true`, `solve_mechanism=delegated_retry` |
| production_ready=false | → true | Multi-task validation across 3+ distinct tasks with pass rate ≥ 50% |
| public_claim_allowed=false | → true | production_ready=true + external audit or independent verification |

---

## Capability Matrix

| Capability | Status | Evidence | Claim Allowed? |
|-----------|--------|----------|---------------|
| Evidence plumbing | PROVEN | C15-4C-2/C15-4D-3 | internal only |
| Contract reuse | PROVEN | C15-4D-0 | internal only |
| Prompt ordering guard | PROVEN | C15-4D-2A/2B | internal only |
| Delegated retry solve | NOT_PROVEN | C15-4D-3 | no |
| Production readiness | false | all C15 reports | no |
| Public claim | false | all C15 reports | no |

---

## Root Cause Judgment

**Model output quality ceiling.**

The blocker is NOT:
- ❌ Route/control issue — routing works correctly
- ❌ Verifier evidence issue — evidence is injected and available
- ❌ Prompt contract issue — SEARCH/REPLACE contract is fully reused
- ❌ Prompt ordering issue — reordering did not help (C15-4D-3)
- ❌ Instrumentation gap — telemetry is sufficient to classify failures

The blocker IS:
- ✅ **Model output quality ceiling** — the 7B model produces semantically reasonable logic (division-by-zero guard, clamping) but consistently outputs wrong Python indentation in the REPLACE block. This is a model capability limitation, not an infrastructure limitation.

Evidence:
- 3/4 attempts: model correctly identifies the fix (if max_val == min_val: return 0.5, clamp output) but indentation is wrong
- 1/4 attempt: SEARCH block mismatch (different failure mode)
- Prompt reordering (C15-4D-2B) had zero effect on failure pattern
- The model's logic understanding is adequate; its syntactic formatting is not

---

## Next-Path Decision

### Selected: Path B — Bounded Provider Comparison: 7B vs 14B on Delegated Retry

**Rationale:**

1. **Infrastructure is proven** — evidence pipeline, contract reuse, candidate isolation, verifier receipt all work. No infrastructure changes needed.
2. **The cleanest independent variable is model size** — 7B produces correct logic with wrong indentation. 14B (`qwen2.5-coder:14b-instruct-q3_K_M`) is already in the local ollama stack and may handle indentation correctly.
3. **Bounded and safe** — comparison requires only running the same benchmark with a different model name. No code changes, no new infrastructure.
4. **Decisive** — if 14B also fails with INDENTATION_SYNTAX_ERROR, the ceiling is confirmed as task-specific (not model-size-specific). If 14B succeeds, delegated_retry solve becomes provable.
5. **Non-destructive** — preserves all existing infrastructure; tests whether the variable that matters (model capability) is the actual blocker.

**Next task after this:**
```
C15-5 Bounded Provider Comparison: 7B vs 14B on Delegated Retry
```

### Rejected Paths

**Path A — Claim Boundary / Close C15:**
Rejected because while the claim boundary is important (and is defined in this report), closing C15 without testing the 14B model would leave the most obvious independent variable untested. The 14B model is already available and may resolve the INDENTATION_SYNTAX_ERROR ceiling. Path B can be run in parallel with claim governance — they are not mutually exclusive.

**Path C — Output Repair Adapter:**
Rejected because:
- A post-hoc indentation fixer would be fragile (Python indentation is context-sensitive)
- It would risk weakening the parser if not carefully gated
- The model already produces correct logic — the problem is formatting, not semantics
- If 14B can format correctly, the adapter is unnecessary
- If 14B cannot, the adapter would mask a real model limitation

**Path D — Stop Delegated Retry Engineering:**
Rejected because:
- The infrastructure is fully proven and valuable
- Delegated retry is strategically important for Local Model Armor (it's the mechanism that uses verifier evidence to improve patches)
- Demoting it now would waste the proven infrastructure investment
- The 14B comparison is cheap and decisive — worth one more bounded experiment

---

## Next Recommended Task

**C15-5 Bounded Provider Comparison: 7B vs 14B on Delegated Retry**

---

## Scope Statement

- **No production code changed.**
- **No tests changed.**
- **No benchmark behavior changed.**
- **No route authority changed.**
- **Parser/verifier/candidate isolation unchanged.**
- **delegated_retry solved NOT_PROVEN.**
- **production_ready=false.**
- **public_claim_allowed=false.**
