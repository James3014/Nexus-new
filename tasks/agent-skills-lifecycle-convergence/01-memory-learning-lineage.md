# Task Card: memory-learning-lineage

artifact_authority: current
owner: James Chen
status: VERIFIED_PENDING_OWNER_REVIEW
task_id: memory-learning-lineage
commit_forbidden: false
commit_required: true
AUTO_CHAIN: false

## Objective

Close the existing-storage memory and learning loop for Lifecycle V1. Every
episode, handoff, and learning closure must preserve task/attempt/action
lineage; failed or uncertain attempts must be parked and never auto-replayed;
retrieved lessons must be attributable; and terminal outcomes may reinforce,
contradict, or retire a lesson without adding a database or a second learning
authority.

## Allowed files

- `nexus/learning/outcome_memory.py`
- `nexus/core/handoff_bundle.py`
- `nexus/services/local_heal/learning_closure_bridge.py`
- `tests/learning/test_outcome_memory_worker_write.py`
- `tests/core/test_handoff_bundle.py`
- `tests/learning/test_learning_closure_effectiveness.py`
- this card and `INDEX.md`

## Forbidden scope

- no new database, schema store, router, provider policy, lifecycle JSON, or
  automatic retry/replay;
- no changes to Gateway, planner, workforce admission, approval, integration,
  protected branches, worktrees, or external Skills;
- no public or production claim from a learning record alone.

## Required behavior

1. Existing JSONL/JSON storage remains the only persistence surface.
2. Records include `task_id`, `attempt_id`, `action_id`, and
   `idempotency_key`, with terminal outcome and `auto_replay_allowed: false`.
3. Handoff records include `last_successful_action`, `uncertain_mutation`, and
   a fail-closed `resume_gate`.
4. Learning writeback is qualified only by terminal evidence; failed/uncertain
   outcomes are parked and cannot be replayed automatically.
5. Retrieved lesson IDs and applied lesson IDs are distinct and attributable.
6. A terminal outcome can classify a lesson as `reinforce`, `contradict`, or
   `retire`; unqualified entries remain internal-only.

## Verification

```text
uv run pytest -q tests/learning/test_outcome_memory_worker_write.py tests/core/test_handoff_bundle.py tests/learning/test_learning_closure_effectiveness.py
git diff --check
git diff --name-status --diff-filter=D
```

## Exit receipt

Bind the receipt to the scoped commit SHA and this card hash. Claim only
`MEMORY_LEARNING_LINEAGE_VERIFIED`; no provider, live connector, approval, or
production closure is implied.

## Verification receipt

- implementation commit: `c78f268da`
- focused suite: `32 passed`
- storage: existing `.nexus/memory/outcome_history.jsonl` and
  `.nexus/reports/learn/learning_closure.jsonl` only; no database added
- lineage: task/attempt/action/idempotency persisted in episode and handoff
  records
- fail-closed: parked/uncertain outcomes set `auto_replay_allowed: false` and
  require reconcile/owner review before resume
- lesson attribution: retrieved and applied IDs are separate; terminal
  outcomes emit reinforce/contradict/retire disposition
- `git diff --check`: pass; tracked deletion audit: empty
- claim ceiling: `MEMORY_LEARNING_LINEAGE_VERIFIED` only

## Block semantics

`RECOVERABLE_BLOCK` preserves the card and evidence for retry. `HARD_BLOCK`
stops mutation for an authority or persistence-contract contradiction.
