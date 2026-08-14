# Task Card: Golden authority drift checker

- artifact_authority: current
- task_id: `github-issue-115-golden-authority-drift`
- source_issue: `#115`
- owner: James Chen
- status: COMPLETE / TERMINAL_RECONCILIATION
- baseline_revision: `4cf1a3519d7937f71a664bd347efd7c4eb0b4d1e`
- historical_baseline: `4cf1a3519d7937f71a664bd347efd7c4eb0b4d1e`
- merge_base: `4cf1a3519d7937f71a664bd347efd7c4eb0b4d1e`
- reconciled_main: `cdf2570ede5ae218f36f886b696c8da45458043a`
- current_main: `cdf2570ede5ae218f36f886b696c8da45458043a`
- block_class: NONE
- frontier_status: TERMINAL_RECONCILIATION
- terminal_marker: `GOLDEN_AUTHORITY_DRIFT_GATE_PROVEN`
- claim_ceiling: `GOLDEN_AUTHORITY_DRIFT_GATE_PROVEN_ONLY`
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_push: true
- worker_may_approve: false
- worker_may_integrate: false
- `AUTO_CHAIN=false`

## Objective

Add a deterministic read-only checker that maps changed local authority sources
to Golden cases and requires one revision-bound truthful disposition per
affected case.

## Inputs and dependencies

- Issue #115 and Owner comment `5253217783`.
- #114 merge `5e2e4f9b651582d51df5d02c270fec712d241124`, proven ancestor of baseline.
- #65 retains corpus/witness semantics ownership.
- Explicit base/head Git refs and a dispositions JSON document.

## Allowed files

- `scripts/ops/check_golden_authority_drift.py`
- `tests/ops/test_golden_authority_drift.py`
- this card and campaign `INDEX.md`

## Forbidden scope

Do not edit Golden evaluator/corpus/workflow, product/runtime, route/planner,
lifecycle, Workforce, claim/release authority, #191, or #143. Do not create a
second evaluator or persistent report authority.

## Required behavior and evidence

- changed mapped sources require exactly one `MAPPING_UPDATED`,
  `FINDING_UPDATED`, or bounded `NO_GOLDEN_IMPACT` row;
- fingerprints bind exact head authority bytes and stale/omitted values block;
- missing refs/files, unsafe paths, malformed/duplicate rows and metadata-only
  finding promotion fail closed;
- unrelated unmapped changes create no broad obligation;
- output is deterministic JSON and checker makes no repository writes.

## Verification

- `uv run pytest -q tests/ops/test_golden_authority_drift.py`
- `uv run pytest -q tests/ops/test_golden_behavior_eval.py tests/golden_behavior/test_corpus.py`
- `uv run ruff check scripts/ops/check_golden_authority_drift.py tests/ops/test_golden_authority_drift.py`
- `uv run ruff format --check scripts/ops/check_golden_authority_drift.py tests/ops/test_golden_authority_drift.py`
- `git diff --check`

## Physical evidence and terminal boundary

- Historical card baseline: `4cf1a3519d7937f71a664bd347efd7c4eb0b4d1e`.
- PR #210 head: `89f4115a392239787d2928d5bc530817d812cfd1`.
- PR #210 merge: `e0289e8baa27df445858d51e09dc758d45fb9c8a`.
- Exact scope: `scripts/ops/check_golden_authority_drift.py`,
  `tests/ops/test_golden_authority_drift.py`, and this card plus INDEX.
- Exact-head workflows: Pytest, Pyright, Bandit, Ruff, and Wiki governance
  completed successfully.
- Focused verification: 21 passed; Ruff check/preview-format, compileall, and
  `git diff --check` passed.
- Owner receipt on Issue #115 records `COMPLETION_RECONCILIATION` /
  `DONE_NO_FOLLOW_UP` with independent exact-head Luna acceptance ACCEPT; the
  PR #210 GitHub review surface records no review.
- Reconciled current main: `cdf2570ede5ae218f36f886b696c8da45458043a`
  (historical verification receipts `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`
  pre-PR236 rebind and `eb668fb76f0c30d8f025db42cdb8e320d556c037`
  from the 2026-08-13 snapshot).

`GOLDEN_AUTHORITY_DRIFT_GATE_PROVEN` proves only the read-only authority-drift
detection gate and its focused tests. It grants no Golden evaluator or corpus
semantics change, no #114 or #65 ownership, no runtime, route, Planner,
lifecycle, Workforce, Candidate acceptance, approval, integration, merge,
release, or production authority. `AUTO_CHAIN=false`.
