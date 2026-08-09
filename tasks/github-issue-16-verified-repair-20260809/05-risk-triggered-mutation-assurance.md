---
artifact_authority: current
owner: James Chen
status: PENDING_G4
task_id: issue16-g5-mutation-assurance
campaign_id: github-issue-16-verified-repair-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/16
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# G5 Risk-Triggered Mutation Assurance

## Objective

Reuse existing mutation assurance to require targeted challenges for Issue #16's
risk triggers and record deterministic `NOT_REQUIRED` only for qualifying low risk.

## Dependencies

G4 adequacy projection contract.

## Allowed files

- `nexus/engine/mutation_assurance.py`
- `tests/engine/test_mutation_assurance.py`

Maximum changed files: 2.

## Forbidden scope

Mutation router/planner, whole-repository mutation by default, verifier authority,
release/public claim gates, routing, approval, or integration.

## Verification

- `.venv/bin/python -m pytest -q tests/engine/test_mutation_assurance.py`
- `git diff --check`

## Required evidence and exit

Risk inputs/decision/reason, targeted records, killed/survived/equivalent counts.
Required missing/survived fails closed; `NOT_REQUIRED` is not mutation PASS.

## Block classification

`RECOVERABLE_BLOCK` for bounded mutation defects; `HARD_BLOCK` for authority conflict.
