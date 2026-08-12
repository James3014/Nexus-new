# Task Card: Golden authority drift checker

- artifact_authority: current
- task_id: `github-issue-115-golden-authority-drift`
- source_issue: `#115`
- owner: James Chen
- status: ACTIVE
- baseline_revision: `4cf1a3519d7937f71a664bd347efd7c4eb0b4d1e`
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

## Exit, block, and residual debt

Exit only with the exact four-file Candidate and independent exact-head review.
`RECOVERABLE_BLOCK` covers test/format defects; `HARD_BLOCK` covers ambiguous
authority, overlap, baseline drift, or required scope widening. CI integration
is residual and requires a separately bounded owner after Candidate behavior is
accepted.

Claim ceiling: `GOLDEN_AUTHORITY_DRIFT_GATE_CANDIDATE_ONLY`.
