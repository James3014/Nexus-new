# Task Card: runtime-memory-learning-closure

artifact_authority: current
owner: James Chen
status: VERIFIED_CANDIDATE
task_id: runtime-memory-learning-closure
commit_required: true
AUTO_CHAIN: false
candidate_commit: 45287f9d05f77efb5a6abfde96ae8db116d3c866
claim_ceiling: IMPLEMENTER_VERIFIED_RUNTIME_MEMORY_LEARNING_CLOSURE_CANDIDATE

verification_receipt:
  base_head: f38efc366624b08d39f9d58e5b20bbfe631d8e68
  card_hash_at_execution: 1ea77999aa3631a916ee40fa8165caf7342f22b98b18a046d53bdbaf71d5e21d
  focused_tests: 5 passed
  affected_regression: 18 passed
  diff_check: PASS
  evidence_scope: terminal_outcome_phase_receipts_qualified_learning_and_non_replayable_memory_lineage
  external_acceptance: DEFERRED_EXTERNAL_ACCEPTANCE

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
