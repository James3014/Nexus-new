---
artifact_authority: current
owner: James Chen
status: COMPLETED
terminal_state: TERMINAL_RECONCILIATION
task_id: github-issue-78-learning-episode-identity
campaign_id: github-issue-78-learning-episode-identity-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/78
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Bind Learning Episode Identity Against Tamper

## Objective

Make `build_nexus_learning_episode` and `validate_nexus_learning_episode`
share one canonical identity helper so the stored `idempotency_key` and
`episode_id` are bound to the episode's semantic payload, and independent
post-build tamper of either mutable field fails closed.

## Inputs and dependencies

- Issue #78 is P1 READY and Owner-authorized (DeepSeek auto-claim queue 2/5).
- Evidence baseline: main `84eaa6886e0388a4e15f5b837c89e37768b14307`.
- Defect confirmed by Owner pre-mutation comment (2026-08-10T02:54:21Z):
  changing `episode_id` alone and changing `idempotency_key` alone are both
  currently accepted.
- Current identity contract: explicit producer `idempotency_key` is preserved;
  otherwise fallback identity is `task_id:attempt_id:action_id:source`;
  `episode_id` is `lep:` plus the first 24 hex characters of SHA-256(identity).
- No exact file overlap with #63 (`learning_effectiveness_measurement.py`).

## Allowed files

- `nexus/contracts/learning_experience.py`
- `tests/learning/test_nexus_learning_episode_contract.py`
- `tasks/github-issue-78-learning-episode-identity-20260810/INDEX.md`
- `tasks/github-issue-78-learning-episode-identity-20260810/01-bind-learning-episode-identity.md`

Maximum changed files: 4.

## Forbidden scope

- learning adapter, learning ledger, effectiveness scorecard
- route/workforce policy, lifecycle, approval, Candidate, CI, or Golden corpus
- schema migration or consumer rewrite
- any file outside the allowed scope above

## Required behavior

- One shared canonical identity helper used by builder and validator.
- Validator recomputes `episode_id` from stored `idempotency_key`.
- Malformed/empty keys and mismatched episode IDs fail closed.
- Existing explicit custom idempotency keys and 24-hex format remain
  compatible.
- task/attempt/action/source changes remain distinct and lesson ordering
  normalization remains deterministic.
- Missing terminal evidence remains ineligible for uplift or outcome claims.

## Verification

- Focused learning episode contract tests including post-build
  identity/idempotency tamper.
- Related learning contract tests and #63 non-overlap check.
- Ruff, Pyright exact-base differential where applicable, `git diff --check`.
- Golden mapping for GB-073 (`test_episode_identity_and_stages_are_stable_and_fail_closed`).
- If a schema migration or consumer rewrite is required, stop and reconcile
  rather than widening.

## Required evidence and exit criteria

- New tamper tests prove independent `episode_id` or `idempotency_key`
  modification fails closed.
- Explicit custom idempotency key episodes remain valid and deterministic.
- Existing stability, applied-lesson bounding, uplift gating, and outcome-memory
  tests still pass.
- Focused suite, related learning tests, static differential gates, diff gate,
  and independent review pass.

Maximum claim: this detects independent post-build field tamper and preserves
deterministic identity. It does not provide authenticity against an actor who
can rewrite both mutable fields consistently; that would require a trusted
immutable envelope or signature.

## Completion receipt

- Task Card authorization commit: `14e88e53d`
- implementation head: `e200cccd6`
- PR: https://github.com/James3014/Nexus-new/pull/84
- shared `canonical_episode_identity` helper used by builder and validator;
  validator recomputes `episode_id` from stored `idempotency_key` and fails
  closed on empty keys, malformed ids, and mismatches
- explicit custom idempotency keys and 24-hex format remain compatible
- verification: 13 focused contract tests; 256 learning/learning_experience
  suite; 9 Golden corpus (GB-073 mapped); 265 total passed
- local_heal consumer sweep: identical 91 pre-existing environment failures on
  base and Candidate (zero regression), 2499 passed
- Ruff exact-base differential: zero new findings (same 3 pre-existing)
- Pyright exact-base differential: prod 20 = base 20; test 39 (base 67)
- `git diff --check`: clean
- reached `CANDIDATE_PR_READY` (PR opened to `main`; no self-approve/merge)

## Terminal reconciliation receipt

Reconciled on fresh main `12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`;
historical baseline preserved at `84eaa6886e0388a4e15f5b837c89e37768b14307`.

- Issue #78 CLOSED/completed; Owner receipts `5235366173`, `5235661276`,
  `5236118747`, and `5253054683`
  (POST_MERGE_CONSUMER_VERIFICATION: clean main `70fd467ab...`, 293 passed,
  6 warnings, exit 0).
- PR #84 merged: base `84eaa6886e0388a4e15f5b837c89e37768b14307`, head
  `310c8db50d7ec0789bef8d30848564f3ef375d55`, merge
  `c304e7d98f62f615f7ca44c2ab4451dff9e780e3`; 4 files, +343/-4; head checks
  terminal success (Governance/Bandit/Ruff/Pyright/Pytest).
- PR84 merge and head are ancestors of current main; current-main source/test
  readback confirms the merged identity-binding contract.

Terminal marker: `LEARNING_EPISODE_IDENTITY_BINDING_PROVEN`.
Claim ceiling: `LEARNING_EPISODE_IDENTITY_BINDING_PROVEN_ONLY` - repository-
contained learning episode identity contract/source/test evidence only; no
learning uplift, runtime, route/Workforce selection, provider/model identity,
approval, integration, merge, release, or production claim.
`AUTO_CHAIN: false`; no further mutation required.

## Block classification

- `RECOVERABLE_BLOCK`: bounded implementation or regression defect.
- `HARD_BLOCK`: acceptance requires schema/authority mutation, consumer
  rewrite, or files outside the frozen scope.
