---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-90-run-group-canonicalization
campaign_id: github-issue-90-run-group-canonicalization-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/90
baseline_main: 0b97df90b
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
block_class: RECOVERABLE_BLOCK
claim_ceiling: WORLD_C_RUN_GROUP_CANONICALIZATION_CANDIDATE_ONLY
---

# Task Card: Canonicalize repair-receipt `run_group`

## Objective

Add one validator/canonicalizer in `receipt.py` and use it at the existing
receipt construction/write seam. Valid identifiers remain distinct and
deterministic. Empty, whitespace, dot/traversal, separator, control,
malformed, and path-like values fail closed before any write or path
interpolation. No empty legacy fallback is retained.

## Allowed files

- `nexus/services/local_heal/receipt.py`
- `tests/unit/test_local_heal_receipt.py`
- this Task Card and `INDEX.md`

Maximum changed files: 4.

## Forbidden scope

No other LocalHeal modules, storage refactors, World C projection, source-hash
contract, planner/topology/workforce/provider changes, CI/workflow, approval,
integration, merge, release, or public/production claim.

## Verification

- RED then GREEN focused receipt tests;
- valid distinct groups produce distinct deterministic receipt identities;
- reject `None`, empty, whitespace, `.`, `..`, traversal, `/`, `\\`, control,
  malformed, and separator-bearing values before writes;
- existing valid receipt serialization remains compatible;
- focused receipt tests, Ruff format/check, compileall, `git diff --check`,
  and exact scope audit.

## Evidence and exit

Bind Candidate evidence to the implementation commit and this card hash.
Worker may commit and push the issue branch but may not approve, integrate, or
merge. Maximum claim is canonicalized fail-closed receipt `run_group` identity
only.
