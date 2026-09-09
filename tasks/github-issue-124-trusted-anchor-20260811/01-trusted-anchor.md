---
artifact_authority: current
owner: James Chen
status: COMPLETE
terminal_state: TERMINAL_RECONCILIATION
purpose: Install the fail-closed three-job trusted deletion-evidence workflow anchor.
issue: 124
---

Historical source-PR current-main binding: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; retained as historical evidence after the Issue #428 active rebind.

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

## Terminal reconciliation

This card is terminally reconciled after physical integration by successor
PR #127, which preserved this candidate chain and added the separately
authorized Issue #126 OpenWiki inventory synchronization:

- PR #127 exact base: `73d7437bfc64b0afd453ef56e46e3467304eb99e`.
- PR #127 exact head: `6d1eb2bf39db537a3f0714dda77ba0c290da11cf`.
- PR #127 merge: `fffc127cbb91bf1d06940f4a021c6e3011e96cce` (Owner exact merge readback; ancestor of current `main`).
- Required checks at exact head: Pytest run `31456046430` success; Pyright/Ruff/Bandit/Wiki runs `31456046*` success.
- Reconciled current `main`: `71ae533ec9f795477131645f96cea1c93b4f4d40`; `trusted-deletion-anchor.yml`, `trusted_deletion_anchor.py`, `test_trusted_deletion_anchor.py`, and the OpenWiki inventory row are present.
- Historical baseline preserved: implementation was bound to `4232478da8061caba1be82b5a213974e840099fa`; final integration was PR #127.
- Historical PR #125 (merge `1301514db`) was superseded by PR #127 due to the exact-base OpenWiki impact failure and is not the integrated merge.
- Marker: `BOOTSTRAP_ANCHOR_INSTALLED`.
- Claim ceiling: `BOOTSTRAP_ANCHOR_ONLY / NO_PROTECTED_PROVENANCE_CLAIM`; merge proved anchor installation only and no protected deletion provenance.
- `AUTO_CHAIN=false`; this record grants no #104/#105/#106, ruleset, runtime, approval, integration, merge, release, or production authority.
