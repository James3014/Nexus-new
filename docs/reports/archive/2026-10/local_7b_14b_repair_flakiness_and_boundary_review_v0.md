# Local 7B/14B Repair Flakiness and Boundary Review v0

## Summary
| Field | Value |
|-------|-------|
| Source Gate | `local_7b_14b_repair_validation_gate_v0` (commit `de5c7730`) |
| Gate Status In | `PASS_WITH_RISK` |
| Review Verdict | `PASS_WITH_CONDITIONS` |
| Gate Status Out | `PASS_WITH_RISK` (unchanged) |
| Expansion Authorized | ❌ No |
| Tasks Expansion-Eligible | 5/6 |

## Evidence Tier Classification

| Task | Evidence Tier | Acceptable for Expansion |
|------|--------------|--------------------------|
| astropy_13236 | `subprocess_python_task_venv_verified` | ✅ |
| astropy_12907 | `subprocess_python_task_venv_verified` | ✅ |
| sympy_13031 | `retry_aware_subprocess_python_task_venv_verified` | ✅ |
| django_core_01 | `subprocess_pytest_nexus_venv_verified` | ✅ |
| concurrency_bug_01 | `env_blocked_code_review_verified` | ❌ |
| concurrency_bug_02 | `stress_test_verified` | ✅ |

## Concurrency Flakiness Detail

### concurrency_bug_01 — `env_blocked_code_review_verified`
- **subprocess_pytest_ran**: `false` — nexus import-time hang blocked execution
- **Verification method**: lock-order static analysis vs. `FixedResourceTransfer` reference
- **Fix correctness**: Logic is provably deadlock-free (canonical AB order for all acquires)
- **flakiness_risk**: `low_or_unknown` — logic correct, empirical test not run
- **Expansion block**: Yes — must be upgraded to `subprocess_pytest_verified` before expansion

### concurrency_bug_02 — `stress_test_verified`
- **subprocess_pytest_ran**: `true`
- **stress_test_count**: 5 tests × 20–50 threads
- **Timeout**: 1500ms
- **flakiness_risk**: `low` — probabilistic but high-iteration stress passed
- **Expansion block**: No

## Retry Attribution — sympy_13031
- **Attempt 1**: exit_code=1, verifier_status=failed (incomplete patch)
- **Attempt 2**: exit_code=0, verifier_status=passed (correct patch)
- **Retry mixed into first-pass success**: ❌ No — two separate receipts, unambiguous
- **Metadata gap**: `retry_count=0` in both receipt rows (should be 1 for attempt 2). Minor. Evidence chain correct.

## Boundary Integrity
All 13 boundary checks: **PASS**  
`gate_status` NOT upgraded from PASS_WITH_RISK to PASS.

## Required Actions Before Expansion
1. Fix env import-time hang → enable subprocess pytest for concurrency_bug_01
2. Re-run `pytest tests/unit/verifiers/concurrency/test_deadlock.py`
3. Upgrade evidence tier → `subprocess_pytest_verified`
4. Fix `retry_count` metadata increment for future runs

## Generated Artifacts
- `evidence_tier_review.json`
- `concurrency_flakiness_review.json`
- `retry_attribution_review.json`
- `boundary_integrity_audit.json`
- `flakiness_review_summary.json`
