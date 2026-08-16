---
artifact_authority: current
owner: James Chen
status: COMPLETE / TERMINAL_RECONCILIATION
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

## Completion evidence

- pre-mutation card hash:
  `3fb0756d08e04568cd446eae36d77c9227ffcb290822ae38643647301d8e2c23`
- implementation commit: `713273bb3`
- Task Card authorization commit: `03ce9d453`
- PR: https://github.com/James3014/Nexus-new/pull/83
- `tests/ops/test_select_tests.py`: 14 passed
- `tests/ops/test_pr_impact_gate.py` + `tests/ops/test_build_test_impact_index.py`: 20 passed
- `tests/nexus/codeintel/test_impact_service.py` + `tests/ops/test_ci_gate_wiki_sync_block.py`: 6 passed
- ops map-governance sweep: 61 passed
- production selector for `nexus/learning/learning_effectiveness_measurement.py`:
  targets `tests/learning` + `tests/services/test_policy_gate.py`, risk `high`,
  reason `learning_contract`, no unmatched path
- unknown path outside `nexus/learning` remains fallback/unmatched
- `git diff --check`: clean

## Terminal reconciliation (2026-08-14)

Owner receipt `5253011891` (POST_MERGE_RECONCILIATION_20260811) binds Issue
#82 CLOSED, PR #83 implementation `713273bb3f8899abdaf65d5aaf4f41041529d1fb`
merged by `b19c80709cadb6f334487f94384930c4d1f09133`, disposition
PRODUCT_COMPLETE / STALE_CARD_ONLY. Current `main`
`46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c` readback confirms the delivered
impact-map row and learning default-map test (prior readback at
`cdf2570ede5ae218f36f886b696c8da45458043a` historical). Terminal marker:
`LEARNING_IMPACT_MAPPING_PROVEN`; claim ceiling:
`LEARNING_IMPACT_MAPPING_PROVEN_ONLY`. This card status update is
governance-metadata-only and grants no product correctness, causal uplift,
runtime, route, Workforce, approval, integration, merge, release, or
production authority.

## Forbidden scope

No selector algorithm, impact classifier, workflow, production, learning
implementation, Task Card scope widening, direct `main` push, self-approval,
self-merge, or production/public claim.
