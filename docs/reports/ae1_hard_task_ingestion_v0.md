# AE1 — Hard Task Ingestion

**Status**: `AE1_HARD_TASK_SET_READY`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

Created a classified task set of 35 candidates covering 6 repos, 12 bug categories, and 7 hard/boundary tasks. The set is designed to stress Nexus boundaries and discover failure classes.

---

## Task Set Quality

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Total candidates | 30+ | 35 | PASS |
| Verifier-reproducible | 20+ | 22 | PASS |
| Real repair tasks | 15+ | 18 | PASS |
| Repos | 5+ | 6 | PASS |
| Bug categories | 8+ | 12 | PASS |
| Hard/boundary tasks | 5+ | 7 | PASS |

---

## Repos Covered

| Repo | Tasks | Source |
|------|-------|--------|
| sympy | 6 | SWE-bench + local |
| astropy | 5 | SWE-bench + local |
| django | 4 | SWE-bench |
| nexus_internal | 18 | Local fixtures |
| flask | 1 | SWE-bench candidate |
| matplotlib | 1 | SWE-bench candidate |

---

## Bug Categories

| Category | Count | Examples |
|----------|-------|----------|
| single_anchor_repair | 15 | C_12481, concurrency_001-008 |
| two_file_coordinated | 1 | django__django-11505 |
| three_plus_file_broad_edit | 1 | django__django-13455 |
| semantic_multi_hop | 1 | sympy__sympy-14096 |
| wrong_receiver_argument | 1 | astropy__astropy-14902 |
| missing_helper_call | 2 | astropy__astropy-13236 |
| wrong_call_order | 2 | django__django-12497 |
| error_handling_overeager_raise | 2 | astropy__astropy-12907 |
| numeric_behavior | 3 | sympy__sympy-14365 |
| output_formatting | 2 | C_13453 |
| API_compatibility | 1 | sympy__sympy-13852 |
| architecture_refactor | 1 | architecture_001 |

---

## Hard/Boundary Tasks

| Task ID | Class | Why Hard |
|---------|-------|----------|
| django__django-13455 | three_plus_file_broad_edit | Governance boundary |
| django__django-11505 | two_file_coordinated | Owner-gated |
| architecture_001 | architecture_refactor | Unsupported |
| environment_001 | environment_sensitive | Env-blocked |
| ambiguous_001 | ambiguous_expected_behavior | Correct abstain |
| missing_repro_001 | missing_reproduction | Unsupported |
| verifier_gap_001 | verifier_unavailable | Verifier gap |

---

## Conclusion

**AE1_HARD_TASK_SET_READY**

Task set is ready for failure boundary benchmark.

---

## Artifacts

- `candidate_task_inventory.json`
- `accepted_task_set.json`
- `rejected_task_set.json`
- `verifier_reproduction_results.json`
- `task_classification.json`
- `boundary_candidate_list.json`
