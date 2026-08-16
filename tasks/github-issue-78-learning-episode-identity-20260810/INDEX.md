---
artifact_authority: current
owner: James Chen
status: COMPLETE
terminal_state: TERMINAL_RECONCILIATION
campaign_id: github-issue-78-learning-episode-identity-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/78
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
ordered_cards:
  - 01-bind-learning-episode-identity.md
current_frontier: null
completed_cards:
  - 01-bind-learning-episode-identity.md
blocked_cards: []
AUTO_CHAIN: false
---

# Issue 78 Learning Episode Identity Binding

Bind Nexus learning episode identity and idempotency fields to their canonical
semantic payload so post-construction tamper fails closed.

Pre-mutation card SHA-256:
`92b4fe3c7235576f5efe397afffcea82ec1a94b196f95dc644592d2e6127a0de`.

Owner directive comment:
https://github.com/James3014/Nexus-new/issues/78#issuecomment-5235661276

Terminal marker: `LEARNING_EPISODE_IDENTITY_BINDING_PROVEN`.

Completion receipt:

- Task Card authorization commit: `14e88e53d`
- implementation head: `e200cccd6`
- PR: https://github.com/James3014/Nexus-new/pull/84
- exact two-file source scope plus Task Card binding
- shared `canonical_episode_identity` helper used by builder and validator
- validator recomputes `episode_id` from stored `idempotency_key`; empty,
  malformed, and mismatched identities fail closed
- explicit custom idempotency keys and 24-hex format remain compatible
- tests: 13 focused contract tests + 256 learning/learning_experience suite
  + 9 Golden corpus (GB-073 mapped) = 265 passed
- local_heal consumer suite: identical 91 pre-existing env failures on base
  and Candidate (zero regression); 2499 passed
- Ruff exact-base differential: zero new findings (same 3 pre-existing)
- Pyright exact-base differential: prod 20 (matches base), test 39 (base 67)
- `git diff --check`: clean
- reached `CANDIDATE_PR_READY` (PR opened to `main`; no self-approve/merge)

## Terminal reconciliation

Reconciled on fresh main `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c` with
historical baselines preserved at
`84eaa6886e0388a4e15f5b837c89e37768b14307` (original) and
`586abbfb459550de912002203ff2911c7a40db58` (prior rebind).

PR285 non-destructive rebind onto current main `46e21858...` (2026-08-16);
scoped metadata blobs byte-identical across rebind.

Post-merge evidence:

- Issue #78 is CLOSED/completed (state_reason=completed) with Owner receipts:
  `5235366173` (pre-mutation defect), `5235661276` (Owner directive),
  `5236118747` (CANDIDATE_PR_READY), `5253054683`
  (POST_MERGE_CONSUMER_VERIFICATION: clean main `70fd467ab...`, 293 passed,
  6 warnings, exit 0).
- PR #84 merged: base `84eaa6886e0388a4e15f5b837c89e37768b14307`, head
  `310c8db50d7ec0789bef8d30848564f3ef375d55`, merge
  `c304e7d98f62f615f7ca44c2ab4451dff9e780e3`; 4 files, +343/-4.
- PR84 head required checks terminal success: Wiki Exact-Base Governance CI,
  Exact-Base Bandit, Exact-Base Ruff, Exact-Base Pyright, Pytest.
- PR84 merge and head are both ancestors of current `nexus-new/main`.
- Current-main physical readback: `nexus/contracts/learning_experience.py`
  contains `canonical_episode_identity` used by builder and validator, with
  fail-closed guards `NEXUS_LEARNING_EPISODE_EMPTY_IDEMPOTENCY_KEY`,
  `NEXUS_LEARNING_EPISODE_MALFORMED_EPISODE_ID`, and
  `NEXUS_LEARNING_EPISODE_IDENTITY_MISMATCH`;
  `tests/learning/test_nexus_learning_episode_contract.py` contains
  tamper/cross-task/malformed/custom-key/determinism/authority tests.

Terminal marker: `LEARNING_EPISODE_IDENTITY_BINDING_PROVEN`.
Claim ceiling: `LEARNING_EPISODE_IDENTITY_BINDING_PROVEN_ONLY` - repository-
contained learning episode identity contract/source/test evidence only; no
learning uplift, runtime, route/Workforce selection, provider/model identity,
approval, integration, merge, release, or production claim.

`AUTO_CHAIN: false`. No open PR overlap; no further mutation required.
