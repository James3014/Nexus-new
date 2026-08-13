# Worker-neutral Ready-Issue claim contract

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

## Block class

`HARD_BLOCK` if implementation requires a canonical claim service, scope
widening, or unresolved overlap with PR #113.
