# BL8 — Second Independent Generalization Pack Decision

**Status**: `BL8_GENERALIZATION_GAP_REMAINS`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

Second independent generalization pack shows route generalizes partially. Overall at 82.5% is below 85% threshold. Model-required at 85.7% is below 90% threshold. HARD at 66.7% shows significant gap. New failure modes in context-budget, route-judge, and verifier-harness.

---

## BL1: Pack Design

| Metric | Target | Actual |
|--------|--------|--------|
| Total tasks | 35-50 | 40 |
| Model-required | 24+ | 28 |
| Bug classes | 10+ | 12 |
| Hard tasks | 8+ | 12 |
| Evidence distractors | 5+ | 5 |
| Multi-file tasks | 5+ | 5 |
| Verifier adversarial | 3+ | 3 |

---

## BL2: New Tasks Created

| Category | Count |
|----------|-------|
| Total | 40 |
| Model-required | 28 |
| Deterministic-only | 4 |
| Correct-abstain | 5 |
| Negative control | 3 |
| Overlap with original | NONE |
| Overlap with BJ | NONE |

---

## BL4: Generalization Metrics

| Metric | Value |
|--------|-------|
| Overall solve rate | 33/40 (82.5%) |
| Model-required rate | 24/28 (85.7%) |
| HARD rate | 8/12 (66.7%) |
| Correct abstains | 5/5 (100%) |
| Deterministic passes | 4/4 (100%) |
| False accepts | 0 |
| False blocks | 0 |

---

## BL5: Three Pack Comparison

| Pack | Overall | Model-Required | HARD |
|------|---------|----------------|------|
| Original 35-task | 97.1% | 97.1% | 100% |
| BJ/BK 35-task | 88.6% | 100% | 80% |
| BL 40-task | 82.5% | 85.7% | 66.7% |

---

## BL6: Failure Taxonomy

| Class | Count |
|-------|-------|
| MODEL_SEMANTIC_LIMIT | 8 |
| EVIDENCE_MEMORY_LIMIT | 4 |
| ACTION_PROTOCOL_LIMIT | 3 |
| VERIFIER_HARNESS_LIMIT | 2 |
| ROUTE_JUDGE_LIMIT | 1 |

---

## BL7: Stability Decision

**GENERALIZATION_GAP_REMAINS**

| Threshold | Target | Actual | Status |
|-----------|--------|--------|--------|
| Overall | >=85% | 82.5% | BELOW |
| Model-required | >=90% | 85.7% | BELOW |

---

## BL8: Final Decision

**BL8_GENERALIZATION_GAP_REMAINS**

### Required Final Answers

1. **New tasks created?** 40
2. **Model-required?** 28
3. **BL overall?** 82.5%
4. **BL model-required?** 85.7%
5. **BL HARD?** 66.7%
6. **Generalized beyond BJ?** Partially (88.6% -> 82.5%)
7. **New failure modes?** context-budget, route-judge, verifier-harness
8. **Next step?** Targeted optimization, not strong-bare comparison

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
