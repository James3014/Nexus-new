---
artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: issue16-g3-regression-binding
campaign_id: github-issue-16-verified-repair-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/16
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# G3 Affected Regression Suite Binding

## Objective

Bind deterministic affected-suite identity/hash and reject empty, compile-only,
unrelated, drifted, or failing regression evidence.

## Dependencies

G2 frozen same-oracle contract.

## Allowed files

- `nexus/services/local_heal/evaluation_gate.py`
- `tests/unit/local_heal/test_verification_failure_taxonomy.py`
- `tests/unit/local_heal/test_runbook_compliance.py`

Maximum changed files: 3.

## Forbidden scope

Second verifier authority, repository-wide suite by default, routing, approval,
integration, release, and public claims.

## Verification

- `.venv/bin/python -m pytest -q tests/unit/local_heal/test_verification_failure_taxonomy.py tests/unit/local_heal/test_runbook_compliance.py`
- `git diff --check`

## Required evidence and exit

Suite manifest/identity/hash, test count, base/Candidate binding, and unioned failure
evidence. Maximum claim: affected-suite regression evidence PASS.

## Block classification

`RECOVERABLE_BLOCK` for bounded suite defects; `HARD_BLOCK` for verifier authority conflict.

## Completion receipt

- Implementation commit: `902d19a3762a35aaa73c6e5e7bc60223b8097c7e`
- Exact-commit independent review: ACCEPT; no P0/P1 findings
- G3 and adjacent G2 suites: 37 passed each
- Mandatory base/Candidate suite-hash, rejection, union-evidence, Ruff
  differential, diff, scope, and deletion gates passed
