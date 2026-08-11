---
artifact_authority: current
owner: James Chen
status: active
purpose: Install the fail-closed three-job trusted deletion-evidence workflow anchor.
issue: 124
---

## Objective

Add one default-branch `pull_request_target` workflow, one trusted controller /
verifier module, and one hostile test module. The workflow may bootstrap the
trusted boundary but cannot claim a protected run or close #104.

## Inputs and dependencies

- Issue #124 complete body and comments.
- Issue #75 foundation and PR #118 evidence-only schema.
- Issue #104 terminal-block and bootstrap dependency comments.
- Fresh remote `main` baseline: `4232478da8061caba1be82b5a213974e840099fa`.

## Allowed files

- `.github/workflows/trusted-deletion-anchor.yml`
- `scripts/ops/trusted_deletion_anchor.py`
- `tests/ops/test_trusted_deletion_anchor.py`
- files in this Task Card directory only

File-count ceiling: one workflow, one module, one test module, and Task Card
files. Any additional file requirement is a fail-closed blocker.

## Forbidden scope

Do not modify `scripts/ops/select_tests.py`, `scripts/ops/pr_impact_gate.py`,
their tests, #75 verifier semantics, rulesets, Apps, lifecycle/Candidate/
approval code, product cleanup, or other workflows.

## Required behavior

- Controller runs from the default-branch `pull_request_target` definition,
  resolves full immutable base/head SHAs and trees, fetches/packages exact Git
  objects without importing or executing head code, and hash-binds every fact.
- Executor is a separate fresh job with `permissions: {}`, no checkout,
  secrets, cache, credentials, or persisted credentials; it downloads only the
  controller bundle and emits strict fixed-schema raw evidence.
- Verifier is a separate trusted job, checks out the default branch with
  `persist-credentials: false`, uses only the trusted module, recomputes the
  bundle/source/raw diff/test inventory/node IDs/digests/status/workflow
  identity, and rejects malformed, missing, stale, replayed, substituted,
  skipped, neutral, cancelled, drifted, or token-bearing evidence.
- Every checkout in the repository uses `persist-credentials: false`.

## Verification

- YAML parse for the new workflow.
- `uv run pytest tests/ops/test_trusted_deletion_anchor.py -q`.
- Ruff check and preview format check for the module/test.
- `python -m compileall scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`.
- `git diff --check`.
- Tracked scope, deletion, staged/unstaged stats, and full staged diff audit.

## Evidence and exit criteria

RED→GREEN hostile tests cover workflow substitution, fork/head drift,
artifact replay/tamper, malformed schema, missing identities,
skipped/neutral/cancelled statuses, and token/credential leakage. PR body must
bind exact base/head/card hashes and evidence, and state exactly
`BOOTSTRAP_ANCHOR_ONLY / NO_PROTECTED_PROVENANCE_CLAIM`.

The worker may commit, push this issue branch, and open a PR to `main` because
Issue #124 grants that collaboration authority. The worker must not merge,
approve, configure rulesets/Apps, or claim #104/protected provenance.

## Block class

`HARD_BLOCK` if the boundary cannot be proven fail-closed within the frozen
file scope. Do not commit speculative workflow code in that case.
