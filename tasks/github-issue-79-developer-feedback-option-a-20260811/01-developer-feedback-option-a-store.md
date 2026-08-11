# Card 01 — Additive DeveloperFeedbackDecision contract/store/emitter

**artifact_authority:** current
**owner:** James Chen
**status:** ACTIVE / IMPLEMENTATION_FRONTIER
**task_id:** `github-issue-79-developer-feedback-option-a-store`
**parent_issue:** `79`
**campaign:** `github-issue-79-developer-feedback-option-a-20260811`
**source_main:** `70fd467ab0d29f4373616a5e98d85b014efcd4de`
**decision:** `OPTION_A_ADDITIVE_COMPATIBILITY`
**AUTO_CHAIN:** false
**claim_ceiling:** `candidate_pr_only`
**block_class:** `RECOVERABLE_BLOCK`

## Objective

Implement the additive `nexus.developer_feedback_decision.v1` typed contract,
POSIX JSONL store, and typed emitter without changing existing
`VerifierSignal`, `FailurePattern`, `FeedbackDirective`, `JsonlEventLogStore`
tail semantics, or generic EventBus behavior.

## Allowed files

- `nexus/feedback/contracts.py`
- `nexus/events/contracts.py`
- `nexus/events/log_store.py`
- `nexus/events/transport.py`
- `tests/events/test_developer_feedback_decision.py`
- this campaign INDEX/card only

Runtime output is limited to the dedicated
`.nexus/events/developer_feedback_decision.v1.jsonl` stream and its sidecar
lock; no checked-in runtime artifacts are permitted.

## Forbidden scope

- PR #112 files/branch/history or any cherry-pick/reuse from it;
- `nexus/feedback/router.py`, runtime callers, `nexus/events/store.py`;
- route, Workforce, lifecycle, retry, approval, Candidate, integration, CI,
  learning, schema migration, or generic EventBus redesign;
- migration/quarantine/repair or automatic follow-up;
- free text, prompts, secrets, direct identifiers, local paths, URLs,
  fragments, control or bidi characters in persisted decision fields;
- treating timestamps, EventBus sequence, observer callbacks, or model output as
  authority.

## Required behavior

- generic publish of reserved `developer_feedback_decision` fails before side
  effects; only the typed emitter writes the dedicated stream;
- strict codes/refs whitelist and recommendation-only false authority flags;
- deterministic KEEP/REVISE/REJECT/INVESTIGATE mapping;
- full strict scan under process `RLock`, then shared/exclusive POSIX `flock`;
- absent/empty genesis only; legacy/wrong schema/blank/non-object/
  duplicate-key/partial/middle/final corruption and chain tamper fail closed
  without repair;
- per-task persisted sequence and parent digest; no wall-clock/EventBus seq
  authority;
- same ID + same canonical request replays without append/notification;
  changed payload conflicts; stale expected tail blocks;
- append, flush, file fsync, and creation-time directory fsync occur inside the
  exclusive transaction;
- callbacks and remote broadcast occur only after storage/subscriber locks;
  notification is best-effort, not durable exactly-once;
- preserve `JsonlEventLogStore.read_recent` tail-then-filter behavior and all
  legacy imports.

## Verification

RED then GREEN focused tests must cover:

1. all six mappings and invalid combinations;
2. extra-field/privacy/reference limits and reserved generic publish zero side effect;
3. genesis/restart and every corruption/tamper class;
4. digest/sequence/tail tamper and stale expected-tail rejection;
5. lock timeout/contention, unsupported `fcntl`, and subprocess same/same plus same/different races;
6. replay no-notify, observer-after-commit, write/fsync uncertainty;
7. record/stream ceilings and legacy EventBus/read_recent compatibility.

Commands:

```bash
uv run pytest -q tests/events/test_developer_feedback_decision.py
uv run pytest -q tests/events tests/feedback
uv run ruff check nexus/feedback/contracts.py nexus/events/contracts.py nexus/events/log_store.py nexus/events/transport.py tests/events/test_developer_feedback_decision.py
uv run python -m compileall -q nexus/feedback/contracts.py nexus/events/contracts.py nexus/events/log_store.py nexus/events/transport.py tests/events/test_developer_feedback_decision.py
git diff --check
```

Before commit, inspect full staged diff, changed-file inventory, and scope
audit. Bind candidate evidence to commit SHA and this card hash. Independent
review remains required; this worker cannot self-approve, integrate, merge, or
claim runtime adoption.

## Exit criteria

- focused RED tests fail before implementation and then GREEN;
- compatibility tests preserve legacy imports and tail-then-filter semantics;
- lock/observer/fsync/corruption/idempotency boundaries are evidenced;
- only allowed files changed;
- commit is candidate-ready and may be pushed/opened as a replacement PR only
  after local verification.
