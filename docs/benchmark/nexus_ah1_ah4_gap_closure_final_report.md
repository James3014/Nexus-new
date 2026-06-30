# Nexus AH1-AH4 Gap-Class Capability Extension — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: AH4_GAP_CLASSES_REDUCED + AH4_BOUNDARY_MAP_UPDATED

---

## Executive Summary

AH1-AH4 gap closures improved automatic solve rate from 57.1% to 65.7%. All three gap classes are now closed.

---

## AH1: Evidence Graph Gap Closure

**Status**: `AH1_EVIDENCE_GRAPH_GAP_CLOSED`

| Metric | Before | After |
|--------|--------|-------|
| Confidence | 65% | 88% |
| Causal Path | incomplete | complete |
| Regression | — | NONE |

---

## AH2: Action Protocol Gap Closure

**Status**: `AH2_ACTION_PROTOCOL_GAP_CLOSED`

| Protocol | Status |
|----------|--------|
| ORDERED_CALL_SEQUENCE | VALIDATED |
| Schema | PASS |
| Applier | COMPATIBLE |
| Rollback | ATOMIC_SEQUENCE |
| Safety | ALL_INVARIANTS_PASS |

---

## AH3: Verifier Gap Closure

**Status**: `AH3_VERIFIER_GAP_CLOSED`

| Verifier | Status |
|----------|--------|
| exception_behavior_verifier | BUILT |
| Reproducible | YES |
| Task Solved | YES |
| Regression | NONE |

---

## AH4: Gap Closure Benchmark

**Status**: `AH4_GAP_CLASSES_REDUCED` + `AH4_BOUNDARY_MAP_UPDATED`

### Performance

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Automatic Solve | 57.1% | 65.7% | +8.6% |
| Gap Classes | 3 | 0 | -3 |
| Model Calls | 1.2 | 1.4 | +0.2 |
| Latency | 25s | 30s | +5s |

### Boundary Map Delta

| Class | Before | After |
|-------|--------|-------|
| automatic | 20 | 23 |
| gap_classes | 3 | 0 |

---

## Updated Capability Boundary

### AUTOMATIC (13 classes)

| Class | Status |
|-------|--------|
| single_anchor_repair | SUPPORTED |
| semantic_multi_hop | SUPPORTED |
| wrong_receiver_argument | SUPPORTED |
| missing_helper_call | SUPPORTED |
| wrong_call_order | SUPPORTED |
| error_handling_overeager_raise | SUPPORTED |
| numeric_behavior | SUPPORTED |
| output_formatting | SUPPORTED |
| API_compatibility | SUPPORTED |
| data_structure_invariant | SUPPORTED |
| evidence_graph_gap | NEWLY CLOSED |
| action_protocol_gap | NEWLY CLOSED |
| verifier_unavailable | NEWLY CLOSED |

### OWNER-GATED (2 classes)

| Class | Status |
|-------|--------|
| two_file_coordinated | OWNER_GATED |
| model_semantic_limit | OWNER_GATED |

### CORRECT-ABSTAIN (2 classes)

| Class | Status |
|-------|--------|
| three_plus_file_broad_edit | CORRECT_ABSTAIN |
| ambiguous_expected_behavior | CORRECT_ABSTAIN |

### UNSUPPORTED (2 classes)

| Class | Status |
|-------|--------|
| architecture_refactor | UNSUPPORTED |
| missing_reproduction | UNSUPPORTED |

---

## What Remains Forbidden

- Public claim: **FORBIDDEN**
- Production release: **FORBIDDEN**
- Training export: **FORBIDDEN**
- Cloud/API execution: **FORBIDDEN**
- Unrestricted multi-file edit: **FORBIDDEN**

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/runtime/ah1_evidence_graph_gap_closure_v0/` | AH1 evidence graph |
| `artifacts/runtime/ah2_action_protocol_gap_closure_v0/` | AH2 action protocol |
| `artifacts/runtime/ah3_verifier_gap_closure_v0/` | AH3 verifier |
| `artifacts/runtime/ah4_gap_closure_benchmark_v0/` | AH4 benchmark |
| `docs/reports/ah1_ah4_*.md` | Reports |

---

## Mandatory Flags

```json
{
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true
}
```
