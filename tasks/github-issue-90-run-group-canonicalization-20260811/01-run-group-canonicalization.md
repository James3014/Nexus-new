---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-90-run-group-canonicalization
campaign_id: github-issue-90-run-group-canonicalization-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/90
baseline_main: 0b97df90bbebbd90d0811d46ba73c47e46fe1878
historical_baseline: 0b97df90bbebbd90d0811d46ba73c47e46fe1878
reconciled_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
current_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
block_class: NONE
completion_marker: WORLD_C_RUN_GROUP_CANONICALIZATION_PROVEN
claim_ceiling: WORLD_C_S1_RUN_GROUP_CANONICALIZATION_PROVEN_ONLY
physical_receipt:
  pull_request: 155
  candidate_head: 000274fe44b0b5ae1250fa7fc0fec0cd673b4e47
  merge_commit: 8e05e0827fe913e3e408f87dc274e005bdc0bf92
  changed_files: 4
  focused_tests: 17
  required_checks: SUCCESS
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

PR #155 head `000274fe44b0b5ae1250fa7fc0fec0cd673b4e47` merged as
`8e05e0827fe913e3e408f87dc274e005bdc0bf92` with the exact four-file scope,
17 focused tests, and required checks successful. This terminal metadata
reconciliation proves only canonicalized fail-closed World C S1 receipt
`run_group` identity. #91 and #95 remain separate; no broader World C,
runtime, route, planner, provider, Workforce, approval, integration, merge,
release, or production claim follows.
