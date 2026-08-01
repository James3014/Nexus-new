# Task Card: runtime-memory-learning-closure

artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
task_id: runtime-memory-learning-closure
commit_required: true
AUTO_CHAIN: false

## Objective

Complete memory/learning lineage using existing storage and writers only:
terminal outcome, phase receipts, candidate/verification refs, retrieved and
applied lessons, qualification and disposition.

## Allowed files

- `nexus/engine/pipeline_crystal.py`
- `nexus/engine/crystallization_service.py`
- `nexus/contracts/learning_experience.py`
- `nexus/contracts/local_memory_hub.py`
- `nexus/learning/skill_store.py`
- `tests/engine/test_runtime_learning_closure.py`

## Verification

```bash
uv run pytest -q tests/engine/test_runtime_learning_closure.py
git diff --check
```

## Exit criteria

No failed attempt overwrites stable knowledge, no mutation auto-replays, and
learning write failure cannot report the primary task as successful. Lessons
graduate only with terminal evidence, repeatability, a prevention rule and
authority qualification.
