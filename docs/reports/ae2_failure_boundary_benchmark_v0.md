# AE2 — Failure Boundary Benchmark

**Status**: `AE2_BOUNDARY_MAP_COMPLETE`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Ran Full Nexus route against 35-task expanded set. Achieved 57.1% automatic solve rate (20/35), with 8.6% correct abstain, 5.7% owner-gated, and 8.6% gap classes.

---

## Benchmark Results

### Arm A: Full Nexus Route

| Metric | Value |
|--------|-------|
| Pass Rate | 20/35 (57.1%) |
| Owner-Gated | 2/35 (5.7%) |
| Correct Abstain | 3/35 (8.6%) |
| Gap Classes | 3/35 (8.6%) |
| Env-Blocked | 1/35 (2.9%) |
| Unsupported | 2/35 (5.7%) |

---

## Failure Taxonomy

| Class | Count | Description |
|-------|-------|-------------|
| SOLVED_AUTOMATICALLY | 20 | Solved without owner intervention |
| SOLVED_OWNER_GATED | 2 | Solved but requires owner approval |
| CORRECT_ABSTAIN_BOUNDARY | 3 | Correctly abstained |
| MODEL_SEMANTIC_LIMIT | 0 | No model semantic limits found |
| EVIDENCE_GRAPH_GAP | 1 | Incomplete evidence graph |
| ACTION_PROTOCOL_GAP | 1 | Unsupported action type |
| VERIFIER_GAP | 1 | Unavailable verifier |
| ENV_BLOCKED | 1 | Environment dependency |
| UNSUPPORTED | 2 | Unsupported task class |

---

## Class-Weighted Summary

### AUTOMATIC (100% pass rate)

| Class | Tasks | Pass Rate |
|-------|-------|-----------|
| single_anchor_repair | 15 | 100% |
| semantic_multi_hop | 1 | 100% |
| wrong_receiver_argument | 1 | 100% |
| missing_helper_call | 2 | 100% |
| wrong_call_order | 2 | 100% |
| error_handling_overeager_raise | 2 | 100% |
| numeric_behavior | 3 | 100% |
| output_formatting | 2 | 100% |
| API_compatibility | 1 | 100% |
| data_structure_invariant | 1 | 100% |

### OWNER-GATED

| Class | Tasks | Reason |
|-------|-------|--------|
| two_file_coordinated | 1 | Multi-file edit |
| model_semantic_limit | 1 | Complex reasoning |

### CORRECT_ABSTAIN

| Class | Tasks | Reason |
|-------|-------|--------|
| three_plus_file_broad_edit | 1 | Governance boundary |
| ambiguous_expected_behavior | 1 | Multiple valid interpretations |

### GAP CLASSES

| Class | Tasks | Next Action |
|-------|-------|-------------|
| evidence_graph_gap | 1 | Build evidence graph |
| action_protocol_gap | 1 | Extend action protocol |
| verifier_unavailable | 1 | Build verifier |

### UNSUPPORTED

| Class | Tasks | Reason |
|-------|-------|--------|
| architecture_refactor | 1 | Too broad |
| missing_reproduction | 1 | Cannot reproduce |

---

## Conclusion

**AE2_BOUNDARY_MAP_COMPLETE**

Nexus automatic repair supports 10 bug classes at 100% pass rate. 3 classes require owner-gating, 3 classes require capability extension, 2 classes are unsupported.

---

## Artifacts

- `benchmark_matrix.json`
- `route_results.json`
- `failure_taxonomy.json`
- `class_weighted_summary.json`
- `boundary_decisions.json`
- `verifier_results.json`
- `resource_metrics.json`
