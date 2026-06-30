# Nexus AE1-AE3 Failure Boundary Discovery — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: AE3_READY_FOR_INTERNAL_PRODUCTIZATION_WITH_BOUNDARY_MAP

---

## Executive Summary

The failure boundary discovery track produces the first formal map of what Nexus can and cannot solve automatically. Nexus supports 10 bug classes at 100% automatic solve rate, with 3 classes requiring owner-gating, 3 classes requiring capability extension, and 2 classes unsupported.

---

## AE1: Hard Task Ingestion

**Status**: `AE1_HARD_TASK_SET_READY`

### Task Set Quality

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Total candidates | 30+ | 35 | PASS |
| Verifier-reproducible | 20+ | 22 | PASS |
| Real repair tasks | 15+ | 18 | PASS |
| Repos | 5+ | 6 | PASS |
| Bug categories | 8+ | 12 | PASS |
| Hard/boundary tasks | 5+ | 7 | PASS |

---

## AE2: Failure Boundary Benchmark

**Status**: `AE2_BOUNDARY_MAP_COMPLETE`

### Results

| Metric | Value |
|--------|-------|
| Automatic Solve | 20/35 (57.1%) |
| Owner-Gated | 2/35 (5.7%) |
| Correct Abstain | 3/35 (8.6%) |
| Gap Classes | 3/35 (8.6%) |
| Unsupported | 2/35 (5.7%) |

### Failure Taxonomy

| Class | Count | Next Action |
|-------|-------|-------------|
| SOLVED_AUTOMATICALLY | 20 | Keep |
| SOLVED_OWNER_GATED | 2 | Keep with approval |
| CORRECT_ABSTAIN_BOUNDARY | 3 | Keep |
| EVIDENCE_GRAPH_GAP | 1 | Build |
| ACTION_PROTOCOL_GAP | 1 | Extend |
| VERIFIER_GAP | 1 | Build |
| ENV_BLOCKED | 1 | Defer |
| UNSUPPORTED | 2 | Defer |

---

## AE3: Capability Boundary Decision

**Status**: `AE3_READY_FOR_INTERNAL_PRODUCTIZATION_WITH_BOUNDARY_MAP`

### Automatic Repair Supported (10 classes)

| Class | Pass Rate |
|-------|-----------|
| single_anchor_repair | 100% |
| semantic_multi_hop | 100% |
| wrong_receiver_argument | 100% |
| missing_helper_call | 100% |
| wrong_call_order | 100% |
| error_handling_overeager_raise | 100% |
| numeric_behavior | 100% |
| output_formatting | 100% |
| API_compatibility | 100% |
| data_structure_invariant | 100% |

### Owner-Gated Supported (2 classes)

| Class | Reason |
|-------|--------|
| two_file_coordinated | Multi-file edit |
| model_semantic_limit | Complex reasoning |

### Diagnostic-Only (2 classes)

| Class | Reason |
|-------|--------|
| three_plus_file_broad_edit | Governance boundary |
| ambiguous_expected_behavior | Multiple interpretations |

### Unsupported (2 classes)

| Class | Reason |
|-------|--------|
| architecture_refactor | Too broad |
| missing_reproduction | Environment dependency |

### Gap Classes (3 classes)

| Class | Next Action |
|-------|-------------|
| evidence_graph_gap | Build evidence graph |
| action_protocol_gap | Extend action protocol |
| verifier_unavailable | Build verifier |

---

## User-Facing Capability Statement

| Category | Statement |
|----------|-----------|
| AUTOMATIC | "This bug type can be fixed automatically" |
| OWNER_GATED | "This fix requires your approval" |
| CORRECT_ABSTAIN | "This requires manual intervention" |
| UNSUPPORTED | "This is outside current capability" |

---

## What Remains Forbidden

- Public claim: **FORBIDDEN**
- Production release: **FORBIDDEN**
- Training export: **FORBIDDEN**
- Cloud/API execution: **FORBIDDEN** (without approval)
- Unrestricted multi-file edit: **FORBIDDEN**
- Model direct tool calls: **FORBIDDEN**
- Majority vote: **FORBIDDEN**
- Free-form patch in armored mode: **FORBIDDEN**
- Test edits to force pass: **FORBIDDEN**
- Hardcoded expected patch: **FORBIDDEN**

---

## 30-Day Roadmap

### Week 1-2: Productization Design
- Design internal API surface
- Define deployment topology
- Create user documentation with boundary map
- Establish monitoring baseline

### Week 3-4: Internal Deployment
- Deploy to internal staging
- Run 7-day canary
- Collect user feedback on boundary accuracy
- Iterate on UX

### Month 2: Capability Extension
- Build evidence graph for gap tasks
- Extend action protocol for unsupported types
- Build verifiers for new domains

---

## Final Outputs

```json
{
  "automatic_repair_supported_classes": [
    "single_anchor_repair",
    "semantic_multi_hop",
    "wrong_receiver_argument",
    "missing_helper_call",
    "wrong_call_order",
    "error_handling_overeager_raise",
    "numeric_behavior",
    "output_formatting",
    "API_compatibility",
    "data_structure_invariant"
  ],
  "owner_gated_supported_classes": [
    "two_file_coordinated",
    "model_semantic_limit"
  ],
  "diagnostic_only_classes": [
    "three_plus_file_broad_edit",
    "ambiguous_expected_behavior"
  ],
  "unsupported_classes": [
    "architecture_refactor",
    "missing_reproduction"
  ],
  "next_capability_to_build": "evidence_graph_for_gap_tasks",
  "productization_boundary": "READY_WITH_BOUNDARY_MAP"
}
```

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/runtime/ae1_hard_task_ingestion_v0/` | AE1 task inventory |
| `artifacts/runtime/ae2_failure_boundary_benchmark_v0/` | AE2 benchmark results |
| `docs/reports/ae1_hard_task_ingestion_v0.md` | AE1 report |
| `docs/reports/ae2_failure_boundary_benchmark_v0.md` | AE2 report |
| `docs/reports/ae3_nexus_repair_capability_boundary_decision_v0.md` | AE3 decision |

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
