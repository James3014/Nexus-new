# AJ1 — Updated Boundary Map Validation

**Status**: `AJ1_BOUNDARY_MAP_VALIDATED`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Validated the post-AH boundary map. All 8 checks pass. 13 automatic classes safe, 2 owner-gated correctly blocked, 2 correct-abstain correctly abstained, 2 unsupported correctly unsupported.

---

## Validation Checks

| Check | Status | Details |
|-------|--------|---------|
| Automatic classes safe | PASS | All 13 classes produce safe repair |
| Owner-gated no auto-apply | PASS | Cannot auto-apply without approval |
| Correct-abstain remains | PASS | Remain abstain/diagnostic |
| Unsupported remains | PASS | Remain unsupported |
| Gap classes truly closed | PASS | Not fixture-specific |
| Regression anchors pass | PASS | C_12481, C_13453 pass |
| Local heal tests pass | PASS | Unit tests pass |
| Flags correct | PASS | public/training/production false |

---

## Automatic Class Results

| Class | Tasks | Safe | Verifier Backed |
|-------|-------|------|-----------------|
| single_anchor_repair | 15 | YES | YES |
| semantic_multi_hop | 1 | YES | YES |
| wrong_receiver_argument | 1 | YES | YES |
| missing_helper_call | 2 | YES | YES |
| wrong_call_order | 2 | YES | YES |
| error_handling_overeager_raise | 2 | YES | YES |
| numeric_behavior | 3 | YES | YES |
| output_formatting | 2 | YES | YES |
| API_compatibility | 1 | YES | YES |
| data_structure_invariant | 1 | YES | YES |
| evidence_graph_gap | 1 | YES | YES |
| action_protocol_gap | 1 | YES | YES |
| verifier_unavailable | 1 | YES | YES |

---

## Owner-Gated Results

| Class | Task | Auto-Apply Blocked | Governance Enforced |
|-------|------|--------------------|--------------------|
| two_file_coordinated | django__django-11505 | YES | YES |
| model_semantic_limit | semantic_limit_001 | YES | YES |

---

## Correct-Abstain Results

| Class | Task | Abstain Correct | Diagnostic Only |
|-------|------|-----------------|-----------------|
| three_plus_file_broad_edit | django__django-13455 | YES | YES |
| ambiguous_expected_behavior | ambiguous_001 | YES | YES |

---

## Unsupported Results

| Class | Task | Unsupported Correct | No Auto-Apply |
|-------|------|---------------------|---------------|
| architecture_refactor | architecture_001 | YES | YES |
| missing_reproduction | missing_repro_001 | YES | YES |

---

## Decision

**AJ1_BOUNDARY_MAP_VALIDATED**

All boundary map classes validated. No regressions, no governance leaks, no ambiguity.

---

## Artifacts

- `boundary_map_validation.json`
- `automatic_class_results.json`
- `owner_gated_results.json`
- `correct_abstain_results.json`
- `unsupported_results.json`
- `regression_results.json`
