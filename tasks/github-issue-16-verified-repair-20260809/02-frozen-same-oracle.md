---
artifact_authority: current
owner: James Chen
status: PENDING_G1
task_id: issue16-g2-frozen-same-oracle
campaign_id: github-issue-16-verified-repair-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/16
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# G2 Frozen Same-Oracle Fail to Pass

## Objective

Freeze exact oracle command/content/source identity before mutation and require the
same oracle to fail on base and pass on Candidate; drift and tamper fail closed.

## Dependencies

G1 physical provenance contract merged into this branch.

## Allowed files

- `nexus/services/local_heal/phases/verification.py`
- `tests/unit/local_heal/test_isolated_verifier.py`

Maximum changed files: 2.

## Forbidden scope

Reproduction implementation, evaluation/World C/mutation files, routing,
approval/integration, and public claims.

## Verification

- `.venv/bin/python -m pytest -q tests/unit/local_heal/test_isolated_verifier.py`
- `git diff --check`

## Required evidence and exit

Oracle identity/hash plus bound base FAIL and Candidate PASS receipts. Base already
passing, Candidate failing, hash tamper, command/source/suite drift all fail closed.
Maximum claim: same-oracle Candidate evidence.

## Block classification

`RECOVERABLE_BLOCK` for bounded verifier defects; `HARD_BLOCK` for authority conflict.
