# Nexus BMC/BMD/BME Larger Heldout Validation — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: BME4_REPAIR_MEMORY_V2_CONFIRMED_NEXT

---

## Summary

| Phase | Status | Finding |
|-------|--------|---------|
| BMC1 | Pack design | 50 tasks, 12 classes |
| BMC2 | Tasks built | 38 model-required, 4 deterministic, 5 abstain |
| BMD1 | Route frozen | Commit 94b275f4 locked |
| BMD2 | Validation run | 78.0% overall |
| BMD3 | Metrics | 78.9% model-required, 55.6% HARD |
| BME1 | Attribution | 7 gaps across 11 failures |
| BME2 | Backlog | RepairMemory v2 (P0) |
| BME3 | Decision | REPAIR_MEMORY_V2 next |
| BME4 | Final | REPAIR_MEMORY_V2_CONFIRMED_NEXT |

---

## Heldout Result

| Metric | Value |
|--------|-------|
| Overall | 78.0% (39/50) |
| Model-required | 78.9% (30/38) |
| HARD | 55.6% (10/18) |

---

## Failure Attribution

| Gap | Count |
|-----|-------|
| REPAIR_MEMORY_GAP | 2 |
| VERIFIER_HARNESS_GAP | 2 |
| ACTION_PROTOCOL_GAP | 2 |
| MODEL_CAPACITY_GAP | 2 |
| EXECUTION_EVIDENCE_GAP | 1 |
| CODE_CONTEXT_GRAPH_GAP | 1 |
| DEPENDENT_EDIT_GRAPH_GAP | 1 |

---

## Next Mechanism

**RepairMemory v2** (P0) - Strongest evidence, highest generality, lowest risk

---

## Reports

- `/Users/jameschen/Downloads/nexus_bmc_final_report.md`
- `docs/reports/bmc_larger_heldout_frozen_validation_v0.md` (in repo)
