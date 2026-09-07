# Task Card: astra-effect-journal-verifier-correction-20260907

artifact_authority: current
task_id: `astra-effect-journal-verifier-correction-20260907`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Correct only the verifier locator of existing source contract tasks/ASTRA-P6B-EFFECT-JOURNAL-20260907/00-astra-runtime-effect-journal-20260907.md SHA256 5a46c1dac818290d315de834d1da29cf8e77278d32043d6a75dfa3320c76ad7b. All original objective, allowed paths, behavior, denial, concurrency, replay, port separation, and source-only claim boundaries remain required unchanged. The original tests/services/test_unified_runtime_replan.py does not exist; its replan and finalize coverage resides in tests/services/test_unified_runtime.py. Replace only that nonexistent locator with the actual full unified_runtime suite, while preserving the complete event/fence and actual process-crash tests. This is a coordinator verifier correction, not waiver of any behavior or permission to create a fake test alias. Qualified base 4887d8f6a3faf50d6b600f2c170526e08d4bf408 plus accepted P6-A 94aaced105ac33a475eb61323b816379633f708d and ongoing P6-B scoped source. Coordinator may transport exact correction card/INDEX bytes onto same isolated P6-B branch after source is frozen. Luna implements only original bounded source contract; controller independently inspects exact final diff and reruns all commands. No external model/provider/API-key/SDK/network invocation, live state, deployment, lifecycle Candidate, approval, integration, push, merge, or production claims. AUTO_CHAIN=false. This correction does not supersede original behavioral requirements.

## Allowed files

- `nexus/services/unified_runtime.py`
- `nexus/events/effect_journal.py`
- `nexus/events/log_store.py`
- `nexus/events/writer_generation.py`
- `nexus/events/transport.py`
- `tests/events/test_effect_journal.py`
- `tests/services/test_unified_runtime_effect_fence.py`
- `tests/integration/test_event_fence_runtime.py`

## Verification commands

```bash
python3 -m pytest -q tests/events/test_event_writer_generation.py tests/core/test_event_bus.py tests/events/test_effect_journal.py tests/services/test_unified_runtime_effect_fence.py tests/integration/test_event_fence_runtime.py
python3 -m pytest -q tests/services/test_unified_runtime.py
python3 -m compileall -q nexus/events nexus/services/unified_runtime.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
