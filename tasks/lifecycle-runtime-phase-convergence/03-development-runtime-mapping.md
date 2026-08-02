# Task Card: runtime-development-mapping

artifact_authority: current
owner: James Chen
status: VERIFIED_CANDIDATE
task_id: runtime-development-lifecycle-mapping
commit_required: true
AUTO_CHAIN: false
candidate_commit: f9bba16b549b57787dd7ae7dc4f46e588e142be9
claim_ceiling: IMPLEMENTER_VERIFIED_RUNTIME_DEVELOPMENT_MAPPING_CANDIDATE

verification_receipt:
  base_head: e30ccb9df6a2e879c4d5cda0403f976c292656e9
  card_hash_at_execution: 9d16050bed08f2e2d0868038db505ebce274b9ac40c2ea5a05aabce46d033529
  focused_tests: 3 passed
  affected_service_tests: 5 passed
  affected_receipt_tests: 3 passed
  diff_check: PASS
  full_service_file: DEFERRED_ENVIRONMENT_TERMINATION_AFTER_PARTIAL_RUN
  evidence_scope: shared_task_attempt_action_identity_and_separate_candidate_integration_claims
  external_acceptance: DEFERRED_EXTERNAL_ACCEPTANCE

## Objective

Bind runtime task/attempt/action identity to the existing development
lifecycle execution receipt without collapsing their authorities or terminal
semantics.

## Allowed files

- `nexus/contracts/lifecycle_action.py`
- `nexus/contracts/unified_runtime_receipt.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/engine/runtime_phase_contract.py`
- `tests/nexus/orchestrator/test_runtime_development_mapping.py`

## Verification

```bash
uv run pytest -q tests/nexus/orchestrator/test_runtime_development_mapping.py
git diff --check
```

## Exit criteria

Runtime success cannot imply Candidate acceptance, acceptance cannot imply
integration, and integration cannot imply production/public claim. Reconnect,
uncertain mutation and definition drift preserve the same identity chain.
