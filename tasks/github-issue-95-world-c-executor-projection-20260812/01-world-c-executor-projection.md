---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-95-world-c-executor-projection
campaign_id: github-issue-95-world-c-executor-projection-20260812
source_issue: https://github.com/James3014/Nexus-new/issues/95
baseline_main: ea8c15293455575b4312b92eeeebc69daa4abbcf
historical_reconciled_main: 12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601
reconciled_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
current_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
AUTO_CHAIN: false
worker_may_commit: true
worker_may_push: true
worker_may_approve: false
worker_may_integrate: false
block_class: NONE
frontier_status: TERMINAL_RECONCILIATION
terminal_marker: WORLD_C_EXECUTOR_PROJECTION_WIRING_PROVEN
claim_ceiling: WORLD_C_EXECUTOR_PROJECTION_WIRING_SOURCE_AND_TESTS_ONLY
---

Historical source-PR current-main binding: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; retained as historical evidence after the Issue #428 active rebind.

# Task Card: Wire canonical World C projection into LocalModel capability executor

## Objective

Consume the existing Issue #90 `canonical_run_group` authority and Issue #91
canonical World C patch projection from the existing LocalHeal capability executor.
Raw pipeline patch text remains diagnostic only. Canonical executor output is rebuilt
from verified source/workspace filesystem state, and invalid run-group or projection
identity/hash evidence fails closed.

## Allowed files

- `nexus/services/local_heal/local_model_capability_executors.py`
- `tests/integration/test_issue95_world_c_executor_projection.py`
- `tests/integration/test_local_model_localheal_pipeline_bridge.py`
- `tests/unit/local_heal/test_localheal_pipeline_provider_contract.py`
- this Task Card
- `INDEX.md`

Maximum changed files: 6.

## Required behavior

- canonicalize a non-empty `run_group` with the existing receipt authority before
  pipeline execution;
- pass that canonical value into the legacy HealContext so the existing pipeline and
  receipt chain consume the same identity;
- never promote raw `pipeline_final_patch` to canonical output;
- rebuild the canonical patch from source/workspace state using the existing World C
  projection owner;
- fail closed on unsafe run-group and source/workspace/patch/hash projection mismatch;
- preserve unaffected LocalHeal executor/provider behavior.

## Forbidden scope

No edits to `receipt.py` or `world_c_receipt.py`; no second patch, receipt, Planner,
Router, verifier, Workforce, or approval authority. No Issue #179 Workforce, Issue
#145 reach, Issue #146 acceptance, Planner, route, Issue #143, benchmark, lifecycle,
release, runtime activation, production/public claim, approval, integration, or merge.

## Verification

- RED then GREEN focused Issue #95 projection/run-group tests;
- focused LocalHeal bridge/provider tests;
- existing canonical receipt and World C projection owner tests;
- Ruff check and format check on changed Python files;
- compileall on changed Python files;
- `git diff --check` and exact changed-file scope audit.

## Physical evidence and terminal boundary

- Historical baseline: `ea8c15293455575b4312b92eeeebc69daa4abbcf`.
- Implementation commit: `339551f88fc3cd4c18b29e551d800175bf1746b4`.
- Focused follow-up test commit: `279567b7fae472d67859181ea7f62f87e0387718`.
- PR #186 head: `d585f43b0b02c3d0f79851f5bcd7f2b359a9d064`.
- PR #186 merge: `facd84753b42d2a4bc00581cab74c19b075c733a`.
- Historical reconciled current main: `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`.
- Previous reconciled current main (historical rebind receipt): `cdf2570ede5ae218f36f886b696c8da45458043a`.
- Reconciled current main: `71ae533ec9f795477131645f96cea1c93b4f4d40`.

`WORLD_C_EXECUTOR_PROJECTION_WIRING_PROVEN` is limited to the canonical World C
executor projection source and focused tests. Historical live check-rollup details were
not recovered by this reconciliation and are not inferred. This marker grants no
receipt-owner, Planner/route, Workforce, provider, runtime, approval, integration,
merge, release, production, or Issue #29 consumption authority. `AUTO_CHAIN=false`.
