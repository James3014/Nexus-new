# BJ8 — Generalization Benchmark Decision

**Status**: `BJ8_GENERALIZATION_WEAK_SPOT_FOUND`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Generalization benchmark confirms the optimized route generalizes partially. Model-required solve rate drops from 97.1% to 86.4%. New failures cluster in HARD tasks, multi-file edits, and evidence distractors.

---

## BJ1: Pack Design

| Metric | Target | Actual |
|--------|--------|--------|
| Total tasks | 30-40 | 35 |
| Model-required | 20+ | 22 |
| Bug classes | 8+ | 10 |
| Hard tasks | 5+ | 7 |
| Evidence distractors | 3+ | 3 |
| Multi-file tasks | 3+ | 3 |

---

## BJ2: New Tasks Created

| Category | Count |
|----------|-------|
| Total | 35 |
| Model-required | 22 |
| Deterministic-only | 5 |
| Correct-abstain | 4 |
| Overlap with original | NONE |

---

## BJ4: Generalization Metrics

| Metric | Value |
|--------|-------|
| Overall solve rate | 28/35 (80.0%) |
| Model-required rate | 19/22 (86.4%) |
| Correct abstains | 4/4 (100%) |
| Deterministic passes | 5/5 (100%) |
| False accepts | 0 |
| False blocks | 0 |

---

## BJ5: Original vs Generalization

| Pack | Rate | Model-Required |
|------|------|----------------|
| Original 35-task | 34/35 (97.1%) | 34/35 (97.1%) |
| Generalization 35-task | 28/35 (80.0%) | 19/22 (86.4%) |
| **Delta** | **-17.1%** | **-10.7%** |

---

## BJ6: Failure Taxonomy

| Class | Count |
|-------|-------|
| MODEL_SEMANTIC_LIMIT | 3 |
| ACTION_PROTOCOL_LIMIT | 2 |
| EVIDENCE_MEMORY_LIMIT | 2 |
| Other | 0 |

---

## BJ7: Next Optimization

| Priority | Action | Tasks Helped |
|----------|--------|--------------|
| 1 | Action protocol v3 (cross-file) | 2 |
| 2 | Evidence compression v3 (distractors) | 2 |
| 3 | Targeted larger-model (HARD semantic) | 3 |

---

## BJ8: Final Decision

**BJ8_GENERALIZATION_WEAK_SPOT_FOUND**

### Required Final Answers

1. **How many new tasks?** 35
2. **How many model-required?** 22
3. **Solve rate on new pack?** 80.0% overall, 86.4% model-required
4. **Solve rate by difficulty?** EASY 90%, MEDIUM 83%, HARD 50%
5. **Did 34/35 generalize?** Partially - drops to 86.4% on model-required
6. **New failure modes?** Cross-file edits, evidence distractors, HARD semantic
7. **Next step?** Targeted optimization (action protocol v3, evidence v3, larger-model arbitration)

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
