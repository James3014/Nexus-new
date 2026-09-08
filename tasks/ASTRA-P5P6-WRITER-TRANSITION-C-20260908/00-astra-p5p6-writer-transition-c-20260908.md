# Task Card: astra-p5p6-writer-transition-c-20260908

artifact_authority: current
task_id: `astra-p5p6-writer-transition-c-20260908`
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

Implement the source-owned task-state production adapter and no-write HTTP bootstrap over the accepted Card B collector boundary, preserving the existing legacy/unactivated auto_reconcile behavior while activated roots require a fresh operation-scoped writer lease and P6C owner context before any state write. Bind the exact loaded task-state root, role, source/process identity, writer generation, hold epoch, and transaction; route _write_state, _create_state, _mutate_state, reconciliation, and direct locked callers through the adapter; retain the no-second-domain-lock rule and deny missing, stale, wrong-thread, replayed, forked, or wrong-root bindings before bytes change. Card B dependency is HEAD 549a85cdadf9ed1c15052c296a1f2c63c5d36ea3 tree d7caa4dc3ef7bfa8c9d0725583bc3484863f5c4f and must be independently accepted before this card is dispatched. Follow approved SOURCE_SPEC_ADDENDUM.md SHA bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6. Acceptance requires meaningful positive, denial, lease-witness, lock-selection, hold/reacquisition, HTTP no-write bootstrap, restart/PARTIAL_UNKNOWN, and legacy regression evidence. Card C may acknowledge and observe a hold but must not release Card B admission or claim ACTIVE; Card F owns cohort release. Source/fixture-only work: no new release, live deployment, writer-transition authority publication, provider/API-key/SDK/Agy/native/network action, main/push/merge/approval/integration, or production claim. AUTO_CHAIN=false. Worker may exact-scoped commit after independent review; cannot approve, integrate, or push.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `nexus/orchestrator/writer_quiescence.py`
- `tests/nexus/orchestrator/test_loaded_task_state_writer.py`
- `scripts/ops/nexus_mcp_gateway_http.py`
- `tests/ops/test_gateway_http_writer_bootstrap.py`

## Verification commands

```bash
python3 -B -m pytest -q tests/nexus/orchestrator/test_loaded_task_state_writer.py tests/ops/test_gateway_http_writer_bootstrap.py
python3 -B -m pytest -q tests/nexus/orchestrator/test_writer_quiescence.py tests/ops/test_writer_quiescence_receipts.py
python3 -B -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_self_hosted_task_service.py
python3 -B -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway_http.py
python3 -B -m pytest -q tests/events/test_state_owner_manifest.py tests/events/test_event_writer_generation.py tests/integration/test_p6c_state_consistency.py
python3 -B -m pytest -q tests/contracts/test_gateway_deployment_contract.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
