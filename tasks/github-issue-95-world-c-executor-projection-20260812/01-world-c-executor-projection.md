---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-95-world-c-executor-projection
campaign_id: github-issue-95-world-c-executor-projection-20260812
source_issue: https://github.com/James3014/Nexus-new/issues/95
baseline_main: ea8c15293455575b4312b92eeeebc69daa4abbcf
AUTO_CHAIN: false
worker_may_commit: true
worker_may_push: true
worker_may_approve: false
worker_may_integrate: false
block_class: RECOVERABLE_BLOCK
claim_ceiling: WORLD_C_EXECUTOR_PROJECTION_WIRING_CANDIDATE_ONLY
---

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

## Evidence and exit

Bind one Candidate commit and PR to this exact baseline and changed-file set. Worker may
commit and push the Issue branch and open a Candidate PR. Worker may not approve,
integrate, merge, release, or claim runtime/production readiness.
