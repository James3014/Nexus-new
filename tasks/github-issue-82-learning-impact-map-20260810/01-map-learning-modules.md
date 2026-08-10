---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-82-map-learning-modules
campaign_id: github-issue-82-learning-impact-map-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/82
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# Map New Learning Modules to Conservative Exact-Base Tests

## Objective

Add a conservative subsystem impact-map rule so an otherwise-unmapped
`nexus/learning/*` production change selects the complete `tests/learning`
suite, while more-specific existing learning-module rules retain precedence by
most-specific-prefix.

## Baseline and dependency

- GitHub `main`: `84eaa6886e0388a4e15f5b837c89e37768b14307`
- PR #80 head `d9bf9fbb14b57378d06bbc7faa6b467cb58bd9e9` is the downstream
  consumer/unlock target; do not edit PR #80's learning implementation.

## Allowed source files

- `docs/testing/test_impact_map.md`
- `tests/ops/test_select_tests.py`

Maximum source files changed: 2. Task Card files are authorization artifacts
and must not be widened.

## Required change

- add one active `high` row mapping the `nexus/learning` subsystem prefix to
  the `tests/learning` suite with risk reason `learning_contract`, placed so
  specific existing learning rows still win by most-specific-prefix precedence;
- no selector algorithm, impact classifier, workflow, production, learning
  implementation, or other documentation changes.

## Verification

- `nexus/learning/new_contract.py` maps to `tests/learning`, with high-risk
  `learning_contract` classification and no unmatched production path;
- existing exact learning-module rows still win by most-specific-prefix;
- unknown paths outside `nexus/learning` remain fallback/`IMPACT_UNKNOWN`;
- `tests/ops/test_select_tests.py` and map-governance checks pass;
- `git diff --check`.

## Exit

Exact commit, exact two-file scope, map-governance checks pass, issue-specific
branch pushed, and a PR opened to `main` on `James3014/Nexus-new`.

## Forbidden scope

No selector algorithm, impact classifier, workflow, production, learning
implementation, Task Card scope widening, direct `main` push, self-approval,
self-merge, or production/public claim.
