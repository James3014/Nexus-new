# Local 7B/14B Repair Failure Analysis and Expansion Plan v0

## Part A — Smoke Batch Outcome Analysis

| Task | Classification | Evidence Tier | Flakiness |
|------|---------------|---------------|-----------|
| astropy_13236 | final_success_first_attempt | subprocess_python_task_venv_verified | none |
| astropy_12907 | final_success_first_attempt | subprocess_python_task_venv_verified | none |
| sympy_13031 | final_success_after_retry | retry_aware_subprocess_python_task_venv_verified | none |
| django_core_01 | final_success_first_attempt | subprocess_pytest_nexus_venv_verified | none |
| concurrency_bug_01 | final_success_after_evidence_upgrade | subprocess_pytest_verified | low |
| concurrency_bug_02 | final_success_stress_verified | stress_test_verified | low |

**Aggregate**: 4 first-attempt, 1 retry, 1 evidence-upgrade. 0 final failures. 0 boundary violations.

## Part B — Failure & Risk Summary

| Bucket | Count | Severity |
|--------|-------|----------|
| verifier_failed_then_recovered | 1 (sympy_13031) | low |
| retry_metadata_gap | 1 (sympy_13031) | minor |
| env_interpreter_mismatch | 1 (concurrency_bug_01) | medium_env |
| evidence_tier_weakness | 1 (concurrency_bug_01) | low_after_upgrade |
| concurrency_flakiness | 1 (concurrency_bug_02) | low |
| MicroVerifier generic python3 gap | system | medium |
| StructuredPacket not wired | system | medium |

## Part C — Capability Interpretation

✅ 6/6 final successful internal repair receipts  
✅ 4 distinct domains covered  
❌ NOT claiming: GPT/Gemini parity, benchmark, production readiness, training eligibility

## Part D — Expansion Readiness

**Decision: `READY_WITH_PRE_EXPANSION_HARDENING`**

All 6 tasks expansion-eligible. Pre-expansion hardening tasks documented (non-blocking).  
Expansion execution requires separate owner approval.

## Part E — Next Batch Candidates (6 tasks)

| # | Task ID | Category |
|---|---------|----------|
| 1 | astropy_14526 | deterministic_patch_task |
| 2 | sympy_polys_01 | deterministic_patch_task |
| 3 | nexus_verifier_http_01 | env_lane_task |
| 4 | nexus_protocol_boundary_01 | transport_authority_task |
| 5 | concurrency_bug_03 | concurrency_repeatability_task |
| 6 | sympy_matrices_abstention_candidate | abstention_candidate |

## Part F — Expansion Guardrails (10 rules)

1. Task-scoped interpreter (no bare python3)
2. MicroVerifier ≠ full verifier
3. Fuzzy candidate fail-closed
4. Canonical recovery attribution separation
5. Retry attribution with attempt_index
6. StructuredPacket wiring or gap declaration
7. Concurrency task requirements (flakiness, no sleep-fix, uv run)
8. No runtime/routing integration
9. No training export/public claim
10. Abstention candidate required per batch
