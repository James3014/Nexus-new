# Task Card: runtime-development-mapping

artifact_authority: draft-successor
owner: James Chen
status: DRAFT_PENDING_OWNER_ACTIVATION
task_id: runtime-development-lifecycle-mapping
commit_required: true
AUTO_CHAIN: false

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
