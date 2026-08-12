---
artifact_authority: current
owner: James Chen
status: active
purpose: Bind extracted executor source to the already verified Git bundle without adding authority.
---

# Task Card: Issue #104 executor exact-Git context

- task_id: `github-issue-104-executor-git-context-20260811`
- issue: `#104`
- protected_run: `31473640721`
- base_sha: `cd65696dda3018326ffd71086cf1cb684c3721b9`
- target: `/private/tmp/nexus-issue104-executor-git-context`
- branch: `codex/issue-104-executor-git-context`
- execution_authority: `GOVERNED_CANDIDATE_REPAIR`
- worker_role: primary implementation plus independent Luna hostile review
- AUTO_CHAIN: false

## Failure delta and objective

The hosted controller built the real lock-bound runtime and the executor loaded
Python 3.12.3, pytest 9.0.3 and all required plugins. It collected 57 tests and
passed 56. The first new failure was
`test_build_plan_binds_exact_head_and_test_inventory_trees`: extracted source
had no Git metadata, so `git rev-parse HEAD` returned 128.

Provide an exact local Git context from the already manifest-bound Git bundle.
Do not change Issue #75 semantics or tests.

## Allowed files

Maximum four files:

1. `scripts/ops/trusted_deletion_anchor.py`
2. `tests/ops/test_trusted_deletion_anchor.py`
3. `tasks/github-issue-104-executor-git-context-20260811/INDEX.md`
4. `tasks/github-issue-104-executor-git-context-20260811/01-executor-git-context.md`

## Required behavior

- Before using either archive, recompute source-archive and Git-bundle digests
  against the controller manifest.
- In the non-Git extracted source directory, initialize only local Git
  metadata, verify the bundle with repository-bound cwd, fetch the fixed base,
  head and workflow refs, and bind detached `HEAD` to the exact manifest head.
- Prove exact commit and tree identities before invoking pytest. Do not checkout,
  reset, merge or mutate extracted source files from Git.
- Preserve executor `permissions: {}`, no secrets, token, credentials, cache,
  network dependency resolution or package installation.
- Preserve controller/executor/verifier separation and all runtime, archive,
  cleanup, tamper, replay and `EXACT_GIT_EVIDENCE_ONLY` fail-closed behavior.

## Required evidence

- RED: valid source/runtime bundle in a non-Git cwd reproduces the root Git
  context failure when bootstrap is omitted.
- GREEN: executor exposes exact `HEAD`, parent, head tree and tests tree from
  the fixed bundle and the selected witness completes.
- TAMPER: missing/modified Git bundle, substituted base/head/workflow ref,
  wrong tree, malformed bundle and attempted source overwrite fail closed.
- Sibling sweep stays limited to selected executor tests and Git-context launch
  assumptions.

## Exact verification

```bash
uv run --no-sync pytest -q tests/ops/test_trusted_deletion_anchor.py
uv run --no-sync ruff check scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py
uv run --no-sync ruff format --check --preview scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py
uv run --no-sync python -m compileall -q scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py
git diff --check
git diff --name-status cd65696dda3018326ffd71086cf1cb684c3721b9...HEAD
```

Before commit inspect the complete staged diff, deletion status and exact
four-file ceiling. Bind candidate evidence to commit SHA and this card hash.

## Exit and claim ceiling

- Exit: scoped commit, required local evidence PASS, independent Luna hostile
  review ACCEPT, normal exact-base PR gates PASS, ordinary exact-head merge.
- Candidate claim: `EXECUTOR_EXACT_GIT_CONTEXT_REPAIR_CANDIDATE`.
- #104/#75 remain open until PR #118 is rebound again and a fresh protected
  controller/executor/verifier run is terminal PASS.
- Any need for checkout, token, network, permissions, cache authority, Issue
  #75 mutation or weaker evidence is `HARD_BLOCK`.
