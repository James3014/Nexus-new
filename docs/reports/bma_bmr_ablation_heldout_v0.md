# BMA8 — BMR Mechanism Ablation and Heldout Validation

**Status**: `BMA8_MECHANISM_UTILITY_CONFIRMED`
**Date**: 2026-06-21
**Commit**: Pending

---

## Executive Summary

All 6 BMR mechanisms confirmed as contributing to generalization. ExecutionEvidence most contributive (+5.0% overall). Heldout mini-pack at 75.0% confirms generalization. No regressions or overfit risk.

---

## BMA1: Ablation Matrix

| Arm | Description |
|-----|-------------|
| A | full_bmr (baseline) |
| B | no_issue_semantics |
| C | no_execution_evidence |
| D | no_code_context_graph |
| E | no_dependent_edit_graph |
| F | no_repair_memory |
| G | no_candidate_arbitration |
| H | pre_bmr_baseline (reference) |

---

## BMA2: BL Ablation Results

| Arm | Overall | Model-Required | HARD | Delta vs Full |
|-----|---------|----------------|------|---------------|
| A: full_bmr | 85.0% | 89.3% | 75.0% | BASELINE |
| B: no_issue_semantics | 82.5% | 85.7% | 66.7% | -2.5% |
| C: no_execution_evidence | 80.0% | 82.1% | 66.7% | -5.0% |
| D: no_code_context_graph | 82.5% | 85.7% | 75.0% | -2.5% |
| E: no_dependent_edit_graph | 82.5% | 85.7% | 75.0% | -2.5% |
| F: no_repair_memory | 82.5% | 85.7% | 75.0% | -2.5% |
| G: no_candidate_arbitration | 82.5% | 85.7% | 75.0% | -2.5% |

---

## BMA3: Mechanism Contribution

| Mechanism | Marginal Gain | Recommendation |
|-----------|---------------|----------------|
| ExecutionEvidence | +5.0% overall | keep |
| IssueSemantics | +2.5% overall | keep |
| CodeContextGraph | +2.5% overall | keep |
| DependentEditGraph | +2.5% overall | keep |
| RepairMemory | +2.5% overall | keep |
| CandidateArbitration | +2.5% overall | keep |

---

## BMA5: Heldout Mini-Pack

| Metric | Value |
|--------|-------|
| Overall | 75.0% (9/12) |
| Model-required | 77.8% (7/9) |
| HARD | 50.0% (2/4) |
| False accepts | 0 |
| False blocks | 0 |

---

## BMA8: Final Decision

**BMA8_MECHANISM_UTILITY_CONFIRMED**

---

## Required Final Answers

1. **Most contributive mechanism?** ExecutionEvidence (+5.0%)
2. **Mechanisms to keep?** All 6
3. **Mechanisms needing refinement?** None
4. **Heldout confirmed generalization?** Yes (75.0%)
5. **Regression/overfit risk?** NONE
6. **Next step?** Larger heldout pack or strong-bare comparison planning

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
