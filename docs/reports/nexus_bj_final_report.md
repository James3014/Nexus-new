# Nexus BJ1-BJ8 Generalization Benchmark — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BJ8_GENERALIZATION_WEAK_SPOT_FOUND

---

## Summary

| Phase | Status | Finding |
|-------|--------|---------|
| BJ1 | Pack defined | 35 new tasks, 10 bug classes |
| BJ2 | Tasks built | 22 model-required, 5 deterministic, 4 abstain |
| BJ4 | Metrics | 80.0% overall, 86.4% model-required |
| BJ5 | Comparison | -10.7% drop from original 97.1% |
| BJ6 | Failures | 3 model-semantic, 2 action-protocol, 2 evidence-memory |
| BJ7 | Next | Action protocol v3, evidence v3, larger-model arbitration |
| BJ8 | Decision | GENERALIZATION_WEAK_SPOT_FOUND |

---

## Generalization Result

| Metric | Original | Generalization |
|--------|----------|----------------|
| Solve rate | 97.1% | 80.0% |
| Model-required | 97.1% | 86.4% |
| HARD tasks | 100% | 50% |

---

## New Failure Modes

| Class | Rate | Tasks |
|-------|------|-------|
| bounded_cross_file_edit | 33.3% | 2 |
| evidence_memory_distractor | 33.3% | 2 |
| HARD semantic | 50% | 3 |

---

## Reports

- `/Users/jameschen/Downloads/nexus_bj_final_report.md`
- `docs/reports/bj_generalization_benchmark_v0.md` (in repo)
