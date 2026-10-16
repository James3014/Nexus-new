# T3.0 Controlled Model-Call Reintroduction Experiment

**Run Group**: T3_0_CONTROLLED_MODEL_CALL_REINTRODUCTION
**Date**: 2026-06-18
**Verdict**: YELLOW

---

## Objective

Execute T3.0 to separate three capabilities:
1. **Deterministic recovery success** (D0)
2. **Canonical span / locked search success** (D0)
3. **Model-generated REPLACE success** (M1/M2)

Core question: Can Qwen/local model produce verifiable, attributable, exportable patch success under Nexus deterministic guards?

## Non-Claims

This is NOT:
- A public benchmark
- A Qwen solve rate
- Comparable to official SWE-bench
- Evidence of model_patch_reward > 0

This IS:
- An internal controlled model-call experiment
- Model success counted only when model_patch_reward=1.0 under strict attribution rules

## Selected Subset (6 tasks)

| # | instance_id | project | canonical_span_source | selection_reason |
|---|-------------|---------|----------------------|------------------|
| 1 | astropy__astropy-12907 | astropy | ast_boundary | ast_boundary canonical recovery |
| 2 | astropy__astropy-13236 | astropy | unified_diff | REMOVE_BLOCK semantic recovery |
| 3 | astropy__astropy-13453 | astropy | locked_search | dependency closure + locked_search |
| 4 | sympy__sympy-13031 | sympy | ast_boundary | repro closure + sympy semantic patch |
| 5 | sympy__sympy-12419 | sympy | locked_search | prior patch_mismatch, T2.8 new |
| 6 | sympy__sympy-13647 | sympy | locked_search | prior patch_mismatch, T2.8 new |

Diversity check: 2 ast_boundary, 1 unified_diff, 3 locked_search, 3 astropy, 3 sympy, 2 patch_mismatch.

## Mode Design

### D0 — Deterministic Baseline Replay
- model_calls=0
- Uses existing deterministic/canonical recovery
- Expected: PASS for all 6

### M1 — Model Shadow Proposal
- model_calls>0 allowed
- Model may generate REPLACE only
- SEARCH must come from canonical span
- Patch applied only in isolated shadow workspace
- **Status: NOT RUN** — requires local Qwen14B endpoint

### M2 — Guarded Model Candidate
- Only runs if M1 produced syntactically valid patch
- Same canonical SEARCH as M1
- No deterministic fallback
- Verification PASS required
- **Status: NOT RUN** — requires M1 success first

## Result Table

| Task | D0 | M1 | M2 |
|------|----|----|-----|
| astropy__astropy-12907 | PASS | NOT_RUN | NOT_RUN |
| astropy__astropy-13236 | PASS | NOT_RUN | NOT_RUN |
| astropy__astropy-13453 | PASS | NOT_RUN | NOT_RUN |
| sympy__sympy-13031 | PASS | NOT_RUN | NOT_RUN |
| sympy__sympy-12419 | PASS | NOT_RUN | NOT_RUN |
| sympy__sympy-13647 | PASS | NOT_RUN | NOT_RUN |

## Deterministic Baseline Stability

D0: **6/6 PASS** — Baseline stable for selected subset.

## Model Patch Candidate Table

| Task | model_patch_reward | model_calls | verification | export_as_model_patch_success |
|------|-------------------|-------------|--------------|-------------------------------|
| (none) | — | — | — | — |

**0 clean model_patch_reward=1.0 candidates** (model infrastructure not available).

## Model Failure Table

| Task | mode | failure_class | failure_reason |
|------|------|---------------|----------------|
| all 6 | M1 | model_infrastructure_not_available | M1 requires local Qwen14B endpoint |
| all 6 | M2 | m1_not_passed | M2 requires M1 success first |

## Reward Attribution Table

| Category | Count |
|----------|-------|
| deterministic_recovery (D0) | 6 |
| model_patch_reward=1.0 | 0 |
| model_failure | 0 (infrastructure gap, not model failure) |
| ambiguous attribution | 0 |

## Export Eligibility Table

| Export Type | Rows |
|-------------|------|
| tool_demonstration / canonical_recovery_success | 6 (D0) |
| model_patch_candidate (requires_human_review) | 0 |
| blocked (attribution ambiguity) | 0 |

## Prompt/Output Hash Table

M1/M2 not executed — no prompt/output hashes.

## Guard Violation Check

- model_calls=0 exported as model success: **0** ✓
- deterministic fallback counted as model success: **0** ✓
- public_claim_allowed=true: **0** ✓
- model-generated SEARCH applied: **N/A** (M1 not run)
- canonical span authority broken: **0** ✓

## Recommendation for T3.1

**YELLOW** — D0 baseline stable, but M1/M2 require model infrastructure.

T3.1 prerequisites:
1. Configure local Qwen14B endpoint for M1 model calls
2. Implement REPLACE-only prompt builder (no SEARCH generation by model)
3. Set up isolated shadow workspace for M1 patch application
4. Run M1 on 6-task subset
5. If M1 produces valid patches, run M2 with strict attribution

T3.1 should NOT expand task count until M1/M2 are validated on the 6-task subset.

---

## Appendix: Script

- **Path**: `scripts/bench/t3_0_controlled_model_call_reintroduction.py`
- **Receipts**: `.nexus/reports/local_heal/*__T3_0_CONTROLLED_MODEL_CALL_REINTRODUCTION__/`
