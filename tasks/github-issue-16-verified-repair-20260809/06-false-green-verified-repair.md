---
artifact_authority: current
owner: James Chen
status: READY
task_id: issue16-g6-false-green-calibration
campaign_id: github-issue-16-verified-repair-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/16
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# G6 False-Green Calibration and Final Reducer

## Objective

Add an evidence-only reducer and fixed calibration for correct, no-op,
compile-only-wrong, overfit, boundary-wrong, and regression-inducing repairs.

## Dependencies

G1-G5 receipts and contracts.

## Allowed files

- `nexus/services/local_heal/verified_repair.py`
- `tests/unit/local_heal/test_verified_repair.py`

Maximum changed files: 2.

## Forbidden scope

Verifier execution, routing, approval, integration, promotion, release, production,
or public-claim authority.

## Verification

- `.venv/bin/python -m pytest -q tests/unit/local_heal/test_verified_repair.py`
- `.venv/bin/python -m pytest -q tests/unit/test_reproduction_phase.py tests/unit/test_reproduction_runner.py tests/unit/local_heal/test_isolated_verifier.py tests/unit/local_heal/test_verification_failure_taxonomy.py tests/unit/local_heal/test_runbook_compliance.py tests/unit/local_heal/test_world_c_root_receipt.py tests/engine/test_mutation_assurance.py tests/unit/local_heal/test_verified_repair.py`
- `git diff --check`

## Required evidence and exit

Stable calibration manifest/hash, per-case outcomes, false-green count/rate, and
upstream receipt refs. All five known-wrong cases must be rejected (FGR 0/5) and
the correct repair accepted. Final states are only `VERIFIED_REPAIR` or
`PARTIALLY_VERIFIED`; `public_claim_allowed=false` always.

## Block classification

`RECOVERABLE_BLOCK` for bounded calibration defects; `HARD_BLOCK` for authority or
evidence-integrity conflict.
