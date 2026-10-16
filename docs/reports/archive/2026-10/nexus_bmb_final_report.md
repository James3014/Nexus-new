# Nexus BMB1-BMB8 Heldout Failure Analysis — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BMB8_BUILD_LARGER_HELDOUT_FIRST

---

## Summary

| Phase | Status | Finding |
|-------|--------|---------|
| BMB1 | Failures frozen | 3 tasks, 3 classes |
| BMB2 | Attribution | MODEL_CAPACITY, EVIDENCE_MEMORY, VERIFIER_HARNESS |
| BMB3 | Cross-pack | Systemic patterns confirmed |
| BMB4 | Backlog | 6 refinements (P0: RepairMemory v2) |
| BMB5 | Next step | Larger heldout first |
| BMB6 | Anti-overfit | 7/7 pass |
| BMB7 | Interpretation | Generalization not yet stable |
| BMB8 | Decision | BUILD_LARGER_HELDOUT_FIRST |

---

## Heldout Failures

| Task | Class | Gap |
|------|-------|-----|
| J002 | semantic_code_change | MODEL_CAPACITY |
| J005 | evidence_memory_distractor | EVIDENCE_MEMORY |
| J012 | verifier_selector_harness | VERIFIER_HARNESS |

---

## Top P0 Refinement

**RepairMemory v2** - Stronger distractor filtering and forgetting control

---

## Reports

- `/Users/jameschen/Downloads/nexus_bmb_final_report.md`
- `docs/reports/bmb_heldout_failure_analysis_v0.md` (in repo)
