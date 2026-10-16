# Nexus BL1-BL8 Second Independent Generalization Pack — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BL8_GENERALIZATION_GAP_REMAINS

---

## Summary

| Phase | Status | Finding |
|-------|--------|---------|
| BL1 | Pack defined | 40 new tasks, 12 bug classes |
| BL2 | Tasks built | 28 model-required, 4 deterministic, 5 abstain |
| BL4 | Metrics | 82.5% overall, 85.7% model-required |
| BL5 | Comparison | -14.6% from original, -6.1% from BJ/BK |
| BL6 | Failures | 8 model-semantic, 4 evidence-memory, 3 action-protocol |
| BL7 | Stability | Gap remains (below 85% threshold) |
| BL8 | Decision | GENERALIZATION_GAP_REMAINS |

---

## Generalization Result

| Metric | Original | BJ/BK | BL |
|--------|----------|-------|-----|
| Overall | 97.1% | 88.6% | 82.5% |
| Model-required | 97.1% | 100% | 85.7% |
| HARD | 100% | 80% | 66.7% |

---

## New Failure Modes

| Class | Rate | Tasks |
|-------|------|-------|
| context_budget_pressure | 0% | 1 |
| route_judge_ambiguity | 66.7% | 1 |
| verifier_harness_adversarial | 66.7% | 1 |

---

## Reports

- `/Users/jameschen/Downloads/nexus_bl_final_report.md`
- `docs/reports/bl_second_generalization_pack_v0.md` (in repo)
