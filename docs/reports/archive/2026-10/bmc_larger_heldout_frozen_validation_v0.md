# BME4 — Larger Heldout Frozen Validation Decision

**Status**: `BME4_REPAIR_MEMORY_V2_CONFIRMED_NEXT`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

50-task heldout pack validated. Overall 78.0%, model-required 78.9%, HARD 55.6%. 11 failures distributed across 7 gaps. RepairMemory v2 confirmed as top P0.

---

## BMC2: Task Pack

| Metric | Target | Actual |
|--------|--------|--------|
| Total tasks | 50 | 50 |
| Model-required | 35+ | 38 |
| Bug classes | 12+ | 12 |
| Hard tasks | 12+ | 18 |
| Correct-abstain | 5+ | 5 |

---

## BMD3: Heldout Metrics

| Metric | Value |
|--------|-------|
| Overall | 78.0% (39/50) |
| Model-required | 78.9% (30/38) |
| HARD | 55.6% (10/18) |
| Correct abstains | 5/5 (100%) |
| Deterministic passes | 4/4 (100%) |
| False accepts | 0 |
| False blocks | 0 |

---

## BME1: Failure Attribution

| Gap | Count |
|-----|-------|
| MODEL_CAPACITY_GAP | 2 |
| REPAIR_MEMORY_GAP | 2 |
| VERIFIER_HARNESS_GAP | 2 |
| EXECUTION_EVIDENCE_GAP | 1 |
| ACTION_PROTOCOL_GAP | 2 |
| CODE_CONTEXT_GRAPH_GAP | 1 |
| DEPENDENT_EDIT_GRAPH_GAP | 1 |

**7 different gaps across 11 failures. Failures are distributed, not clustered.**

---

## BME2: Top-3 Mechanism Backlog

| Mechanism | Priority | Failure Count |
|-----------|----------|---------------|
| RepairMemory v2 | P0 | 4 |
| CandidateArbitration v2 | P0 | 3 |
| ExecutionEvidence v2 | P1 | 2 |

---

## BME3: Next Mechanism Decision

**REPAIR_MEMORY_V2_CONFIRMED_NEXT**

RepairMemory v2 has strongest evidence (4 failures), highest generality, and lowest risk.

---

## BME4: Final Decision

**BME4_REPAIR_MEMORY_V2_CONFIRMED_NEXT**

---

## Required Final Answers

1. **New heldout tasks?** 50
2. **Model-required?** 38
3. **Overall solve rate?** 78.0%
4. **Model-required solve rate?** 78.9%
5. **HARD solve rate?** 55.6%
6. **Dominant failure class?** Distributed across 7 gaps
7. **Top-3 mechanism gaps?** RepairMemory, CandidateArbitration, ExecutionEvidence
8. **RepairMemory v2 still top P0?** Yes
9. **Next mechanism?** RepairMemory v2
10. **Gemini/GPT comparison premature?** Yes

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
