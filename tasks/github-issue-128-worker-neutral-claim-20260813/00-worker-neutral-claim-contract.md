# Worker-neutral Ready-Issue claim contract

- status: COMPLETED
- historical baseline: `96bb71e89a0b5112a7b54ab6a3f4ff1ed879f857`
- reconciled/current main: `cdf2570ede5ae218f36f886b696c8da45458043a`
- terminal marker: `WORKER_NEUTRAL_READY_ISSUE_CLAIM_CONTRACT_PROVEN`
- claim ceiling: `WORKER_NEUTRAL_READY_ISSUE_CLAIM_CONTRACT_PROVEN_PROJECTION_ONLY`
- AUTO_CHAIN: false

## Objective

Replace Codex-specific Ready-Issue ownership prose with a worker-neutral,
fail-closed claim contract. Keep claim intent, repository enforcement, and
effective dispatch mode distinct without implementing an atomic claim service.

## Allowed files

- `AGENTS.md`
- `docs/agents/TASK_EXECUTION_CONTRACT.md`
- `tests/ops/test_bootstrap_authority_files.py`
- this campaign card and `INDEX.md`

## Forbidden scope

No claim service, scheduler, route or Workforce selector, #98 Target
concurrency, lifecycle JSON/API, approval/integration/merge, runtime,
release, production claim, or historical Issue/PR rewrite. Do not touch #191
or #143.

## Verification and evidence

- focused bootstrap-authority tests
- `git diff --check`
- staged diff and deletion audit
- independent hostile review of worker-neutrality, fail-closed semantics, and
  authority separation

## Exit criteria

Scoped commit and issue-branch PR only. The resulting contract proves that
`PROJECTION_ONLY`/`UNKNOWN` cannot authorize autonomous mutation and that a
future atomic claim must bind the exact Issue/attempt before mutation.

## Completion receipt

PR #225 head `f045bce3984fecfd498a603e3b311b0de284f0d5` merged as
`82b904a730095494213ad1dc6c54bcb09b798a47`. The exact five-file change had
zero deletions; required checks completed successfully with Tier3 skipped as
expected, and an independent post-merge acceptance confirmed the bounded
worker-neutral vocabulary and fail-closed `MANUAL_DISPATCH` semantics.

This marker does not prove or authorize #129 atomic claim enforcement, a #130
consumer, #98 Target concurrency, autonomous mutation, route or Workforce
selection, lifecycle approval, integration, merge, runtime, release, or
production truth.

## Block class

`HARD_BLOCK` if implementation requires a canonical claim service, scope
widening, or unresolved overlap with PR #113.
