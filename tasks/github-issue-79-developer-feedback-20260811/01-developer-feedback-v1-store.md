---
task_id: issue-79-developer-feedback-v1
campaign_id: github-issue-79-developer-feedback-20260811
artifact_authority: current
owner: James Chen
status: active
worker: codex_luna
commit_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
AUTO_CHAIN: false
---

# Objective

Implement the accepted `nexus.developer_feedback_decision.v1` codes-and-refs
contract, dedicated POSIX JSONL store, and typed EventBus emitter for Issue #79.
The capability remains recommendation-only and is not wired to runtime callers.

## Allowed files

- `nexus/feedback/contracts.py`
- `nexus/events/contracts.py`
- `nexus/events/log_store.py`
- `nexus/events/transport.py`
- `tests/events/test_developer_feedback_decision.py`
- this campaign INDEX and Task Card only

## Forbidden

No router/runtime caller, legacy EventStore, lifecycle/learning/retry/approval,
route/workforce, migration/repair/quarantine, CI, or broad EventBus rewrite.
No self-approval, self-merge, protected-main mutation, or production claim.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/events/test_developer_feedback_decision.py`
- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/core/test_event_bus.py`
- ruff on the five allowed source/test files
- compileall on the four allowed source files
- `git diff --check`
- tracked deletion audit and exact allowed-path audit

## Evidence and claim ceiling

Record RED baseline before implementation and GREEN results after implementation
in the worker handoff/PR. Claim only source-tested dedicated contract/storage/
typed-emitter capability for supported cooperative local POSIX writers. Do not
claim runtime adoption, distributed/hostile-writer safety, guaranteed hardware
durability, durable delivery, verifier/approval/lifecycle/learning truth,
integration, production readiness, or global authority.

## Exit

Scoped commit and Candidate PR to `main`; stop for Owner review. The worker may
push the issue branch and open the PR but may not approve or merge it.
