---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-78-learning-episode-identity-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/78
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
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
- PR: https://github.com/James3014/Nexus-new/pull/PENDING
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
