# Nexus BMA1-BMA8 BMR Mechanism Ablation — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMA8_MECHANISM_UTILITY_CONFIRMED

---

## Summary

| Phase | Status | Finding |
|-------|--------|---------|
| BMA1 | Ablation matrix | 7 arms defined |
| BMA2 | BL ablation | ExecutionEvidence most contributive |
| BMA3 | Contribution analysis | All 6 mechanisms keep |
| BMA4 | Heldout mini-pack | 12 new tasks |
| BMA5 | Heldout results | 75.0% overall |
| BMA6 | Stability | Generalization confirmed |
| BMA7 | Governance | 9/9 checks pass |
| BMA8 | Final decision | UTILITY_CONFIRMED |

---

## Ablation Results

| Mechanism | Marginal Gain |
|-----------|---------------|
| ExecutionEvidence | +5.0% |
| IssueSemantics | +2.5% |
| CodeContextGraph | +2.5% |
| DependentEditGraph | +2.5% |
| RepairMemory | +2.5% |
| CandidateArbitration | +2.5% |

---

## Heldout Validation

| Metric | Value |
|--------|-------|
| Overall | 75.0% (9/12) |
| Model-required | 77.8% (7/9) |
| HARD | 50.0% (2/4) |

---

## Reports

- `/Users/jameschen/Downloads/nexus_bma_final_report.md`
- `docs/reports/bma_bmr_ablation_heldout_v0.md` (in repo)
