# Task Card: astra-p6c-compat-fix-20260908

artifact_authority: current
task_id: `astra-p6c-compat-fix-20260908`
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

Repair four baseline-existing test-fixture model drift failures needed by the approved P5/P6 source compatibility verifier. Exact frozen source8f2baa4cd7711818321263dd3f8f923482d131f8. In only the listed test file derive valid request/receipt expected model and worker identity from the actual test admission binding, replacing outdated hardcoded gemini-3.6-flash-high fixture values. Preserve tampered-model rejection, provider/preflight call-count assertions and card-drift/fallback denial intent; do not weaken production admission or convert failing tests to skipped. No production source/policy/model routing edits. Tests use existing mocks only; no actual Agy/Gemini/provider/API-key/SDK/native/network calls. No live-state/deployment/config/main/push/merge/approval/integration. Worker may scoped source commit after successful checks; independent controller acceptance required. Full P6C compatibility tests must rerun with durable JUnit and exactrevision.

## Allowed files

- `tests/nexus/orchestrator/test_self_hosted_task_service.py`

## Verification commands

```bash
python3 -B -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py
python3 -B -m pytest -q tests/events/test_state_owner_manifest.py tests/events/test_log_store_generation.py tests/integration/test_p6c_state_consistency.py tests/nexus/orchestrator/test_self_hosted_state_owner.py tests/core/test_event_bus.py tests/events/test_effect_journal.py tests/events/test_event_writer_generation.py tests/integration/test_event_fence_runtime.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/services/test_unified_runtime_effect_fence.py tests/services/test_unified_runtime.py tests/services/test_mainchain_entry.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
