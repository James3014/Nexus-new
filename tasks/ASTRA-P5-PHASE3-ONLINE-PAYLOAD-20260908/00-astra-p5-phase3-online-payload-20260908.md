# Task Card: astra-p5-phase3-online-payload-20260908

artifact_authority: current
task_id: `astra-p5-phase3-online-payload-20260908`
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

Apply accepted three-file online-payload extraction onto independently accepted P6C source803793a3b80381515aa6967ef6f05c506260079c at exact isolated staging root. Patch SHA256 ea180956a99c01be1e71f3adca9f6e451ae0ced6c1399ef62bf4d414b41e5c8e. Preserve P6C owner/effect and newer source behavior via semantic deltas, no wholesale existing donor replacement. Keep legacy re-export identity/patchpoint, exact normalization and non-delivery behavior, dependency-light helper. No caller rewrite, Planner/admission/authority change, provider/native/API-key/SDK/Agy/network, state/deploy/config/main/push/merge/approval/integration. Source-only evidence; P5livecutover remains separate. Worker may exactscopedcommit afterverifiers, rootindependentacceptance. Frozen acceptance runner SHA e6f8c16c3e51d8c24bc49db2feb5a86d66df0912fe7af611cef5bb8cb6de30e8 must not change. Run full P6C/P5 compatibility suite and differential AST/cases with durable evidence.

## Allowed files

- `nexus/services/unified_runtime.py`
- `nexus/services/online_payload_contract.py`
- `tests/services/test_online_payload_contract.py`

## Verification commands

```bash
python3 -m pytest -q tests/services/test_online_payload_contract.py tests/services/test_online_auth_non_delivery.py tests/services/test_unified_runtime.py tests/services/test_mainchain_entry.py
python3 -m pytest -q tests/events/test_state_owner_manifest.py tests/events/test_log_store_generation.py tests/integration/test_p6c_state_consistency.py tests/nexus/orchestrator/test_self_hosted_state_owner.py tests/core/test_event_bus.py tests/events/test_effect_journal.py tests/events/test_event_writer_generation.py tests/integration/test_event_fence_runtime.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/services/test_unified_runtime_effect_fence.py tests/services/test_unified_runtime.py tests/services/test_mainchain_entry.py tests/services/test_online_payload_contract.py tests/services/test_online_auth_non_delivery.py
python3 /Users/jameschen/.codex/visualizations/2026/09/07/01a07a25-4ffe-70c3-a098-9ac3818b9562/astra-implementation-current/evidence/coordinator/online_payload_acceptance.py --source-root /private/tmp/astra-p5p6-live-staging-20260908 --base 803793a3b80381515aa6967ef6f05c506260079c
python3 -m compileall -q nexus/services/unified_runtime.py nexus/services/online_payload_contract.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
