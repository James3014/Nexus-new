# MEMORY-EVAL-10: Outcome-Oriented Memory Candidate Selection

**Eval ID**: `MEMORY_EVAL_10_OUTCOME_CANDIDATE_SELECTION_v0`  
**Date**: 2026-06-22  
**Prior Commit**: `e8257f4d` (MEMORY-EVAL-9 real model A/B)

---

## Objective

Identify 3–5 candidate tasks from existing local evidence pools where memory injection has a plausible chance of changing verifier outcome (solved=false → solved=true). This stage is a **selection gate only** — no model calls are made, no outcome is claimed.

The key correction from MEMORY-EVAL-9: **C_12481** showed real model output delta but no solved delta. Rather than re-running C_12481, we apply objective scoring to find better candidates.

---

## Candidate Pool

Scanned **13 candidates** from:

| Source | Tasks Found |
|---|---|
| `eval_substrate_1b_runtime_wiring_v0/runs/` | C_1, C_12481 |
| `be_targeted_14b_action_protocol_v0/tasks/` | C_15020–C_15320 (11 tasks) |
| `.nexus/memory/task/episodes/` | 14 memory cards across C_12481, C_13453 |

---

## Selection Criteria (Scoring Rules)

| Rule | Weight | Description |
|---|---|---|
| R1 | 40 | Task-specific memory available |
| R2 | 30 | Prior verifier FAIL |
| R3 | 20 | No prior real model A/B tested |
| R4 | 10 | memory_off arm missing |
| Minimum score | 50 | Required to select |

---

## Selected Candidates (3)

### 1. C_13453 — Score: 90 ✅ **TOP PRIORITY**

- **Memory cards**: 13 task-specific episodes
- **Top retrieval ID**: `lh-13453` (precision verified in MEMORY-EVAL-7)
- **Prior A/B status**: Never run with real model
- **Why selected**: Largest task-specific memory pool. Memory retrieval is confirmed. This is the most likely candidate for a real outcome delta.
- **Risk**: Pipeline must be instrumented for C_13453 memory injection

### 2. C_1 — Score: 70 ✅

- **Memory cards**: 1 (`lh-finalize`, non-task-specific)
- **Prior status**: memory_on arm FAIL in `eval_substrate_1b`
- **memory_off arm**: Never run — incomplete A/B pair
- **Why selected**: Completing the missing memory_off arm gives a clean comparison. Low cost.
- **Risk**: `lh-finalize` is generic, not task-specific — delta may be noise

### 3. C_15080 — Score: 50 ✅

- **Memory cards**: 0 (none in `.nexus/memory`)
- **Prior status**: All 4 arms FAIL in `be_targeted_14b_action_protocol_v0`
- **Why selected**: Tests whether seeded failure patterns from `failure_memory.py` can change outcome even without task-specific memory
- **Risk**: High setup cost. May not produce outcome delta. Lower priority for MEMORY-EVAL-11.

---

## Rejected Candidates

| Task | Reason |
|---|---|
| C_12481 | Already tested in MEMORY-EVAL-9. Both arms FAIL, no solved delta. |
| C_15020–C_15320 (10 tasks) | Structurally identical to C_15080. Redundant — C_15080 selected as representative. |

---

## Memory Availability Summary

| Task | Cards | Task-Specific | Retrievable |
|---|---|---|---|
| C_13453 | 13 | ✅ | ✅ |
| C_12481 | 1 | ✅ | ✅ (used in eval-9) |
| C_1 | 1 | ❌ (lh-finalize) | ✅ |
| C_15080–C_15320 | 0 | ❌ | ❌ |

---

## Recommended MEMORY-EVAL-11 Execution Order

1. **Start with C_13453** — top memory count, task-specific, never tested. Highest signal potential.
2. **Then C_1** — completes missing memory_off arm. Low cost.
3. **C_15080** — only if C_13453 and C_1 complete cleanly.

---

## Claim Boundary

```json
{
  "real_model_call_executed": false,
  "outcome_uplift_observed": false,
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true,
  "validation_status": "MEMORY_EVAL_10_OUTCOME_CANDIDATE_SELECTION_COMPLETE"
}
```
