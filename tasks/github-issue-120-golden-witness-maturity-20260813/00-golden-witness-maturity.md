# Task Card: Golden witness maturity projection

- artifact_authority: current
- task_id: `github-issue-120-golden-witness-maturity`
- source_issue: `#120`
- owner: James Chen
- status: ACTIVE
- baseline_revision: `e0289e8baa27df445858d51e09dc758d45fb9c8a`
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_push: true
- worker_may_approve: false
- worker_may_integrate: false
- `AUTO_CHAIN=false`

## Objective

Add a deterministic, read-only maturity projection that consumes ordered
`nexus.golden_behavior_eval.v1` reports. Require three consecutive exact clean
runs before a covered witness is `STABLE`, without creating a second evaluator
or changing Golden behavior/evidence status.

## Inputs and dependencies

- Issue #120 and Owner comment `5253217626`.
- #114 merge `5e2e4f9b651582d51df5d02c270fec712d241124`, proven ancestor of baseline.
- Ordered historical evaluator reports; `K=3` is frozen for this Candidate.
- #65 remains semantic witness authority; #115 remains authority-drift owner.

## Allowed files

- `scripts/ops/check_golden_maturity.py`
- `tests/ops/test_golden_maturity.py`
- this card and campaign `INDEX.md`

## Forbidden scope

Do not edit the Golden evaluator, corpus, workflow, #114, #115, #65, product or
runtime code, routes/planner, lifecycle, Workforce, acceptance/claim/release
authority, #191, or #143. Do not execute tests/providers or persist history.

## Required behavior and evidence

- one or two clean exact-identity runs remain `CANDIDATE`; three become `STABLE`;
- attributable failures, infrastructure/unattributed failure, collection drift,
  flake, identity change, and malformed/contradictory input remain distinct;
- duplicate keys/cases/node IDs, invalid hashes/counts/statuses, or ambiguous
  evidence fail closed;
- maturity preserves `covered` / `finding`; findings cannot become covered or
  qualify as stable;
- output is deterministic JSON, revision/test-identity bound, and causes no
  repository or report-history writes.

## Verification

- `uv run pytest -q tests/ops/test_golden_maturity.py`
- `uv run pytest -q tests/ops/test_golden_behavior_eval.py tests/golden_behavior/test_corpus.py`
- `uv run ruff check scripts/ops/check_golden_maturity.py tests/ops/test_golden_maturity.py`
- `uv run ruff format --check scripts/ops/check_golden_maturity.py tests/ops/test_golden_maturity.py`
- `git diff --check`

## Exit, block, and residual debt

Exit only with the exact four-file Candidate and independent exact-head review.
`RECOVERABLE_BLOCK` covers test/format defects; `HARD_BLOCK` covers ambiguous
evidence, overlap, baseline drift, or scope widening. Durable CI history
collection and scheduled requalification remain separately bounded residual
work; this Candidate consumes explicit report history only.

Claim ceiling: `TEST_GOVERNANCE_CANDIDATE_PR_ONLY`.
