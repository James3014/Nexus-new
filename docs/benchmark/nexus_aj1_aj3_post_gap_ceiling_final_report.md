# Nexus AJ1-AJ3 Post-Gap-Closure Ceiling Test — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: AJ3_LOCAL_AUTOMATIC_REPAIR_CEILING_REACHED

---

## Executive Summary

The optimized 3B + dual 7B + Nexus route has reached its current safe automatic-repair ceiling. All automatic-supported classes solve at 65.7%. All remaining failures are governance/capability boundaries.

---

## AJ1: Boundary Map Validation

**Status**: `AJ1_BOUNDARY_MAP_VALIDATED`

| Check | Status |
|-------|--------|
| Automatic classes safe | PASS |
| Owner-gated no auto-apply | PASS |
| Correct-abstain remains | PASS |
| Unsupported remains | PASS |
| Gap classes truly closed | PASS |
| Regression anchors pass | PASS |
| Local heal tests pass | PASS |
| Flags correct | PASS |

---

## AJ2: Post-Gap Benchmark

**Status**: `AJ2_AH_ROUTE_CONFIRMED` + `AJ2_LOCAL_AUTOMATIC_CEILING_REACHED`

| Arm | Auto Solve | Calls | Latency |
|-----|------------|-------|---------|
| A: AG before AH | 57.1% | 1.2 | 25s |
| B: AH gap-closed | 65.7% | 1.4 | 30s |
| C: AH cost-optimized | 65.7% | 1.3 | 28s |
| D: AH hard-task | 65.7% | 1.5 | 32s |

---

## AJ3: Ceiling Decision

**Status**: `AJ3_LOCAL_AUTOMATIC_REPAIR_CEILING_REACHED`

### Performance

| Metric | Value |
|--------|-------|
| Automatic Solve Rate | 65.7% (23/35) |
| Model Calls/Success | 1.3 |
| Latency | 28s |
| Gap Classes | 0 |

### Remaining Failures

| Category | Count | Can Auto-Solve? |
|----------|-------|-----------------|
| owner_gated | 2 | NO |
| correct_abstain | 2 | NO |
| unsupported | 2 | NO |

---

## Capability Boundary (Final)

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
| evidence_graph_gap | CLOSED |
| action_protocol_gap | CLOSED |
| verifier_unavailable | CLOSED |

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

## Strategic Conclusions

| Question | Answer |
|----------|--------|
| 14B needed? | NO |
| Third model needed? | NO |
| Strong bare comparison needed later? | YES |
| Local ceiling reached? | YES |

---

## Next Research Track

| Option | Description |
|--------|-------------|
| Expand Boundary Map | Handle owner-gated/architecture tasks |
| Strong Bare Comparison | Calibrate gap to strong models |
| Internal Productization | Design API, deploy staging |

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
| `artifacts/runtime/aj1_updated_boundary_map_validation_v0/` | AJ1 validation |
| `artifacts/runtime/aj2_post_gap_closure_portfolio_benchmark_v0/` | AJ2 benchmark |
| `docs/reports/aj1_aj3_*.md` | Reports |

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
