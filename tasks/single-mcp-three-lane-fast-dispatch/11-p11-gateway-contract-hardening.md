# Task Card P11: Gateway Contract and Telemetry Hardening

## Identity

- task_id: `single-mcp-three-lane-p11-gateway-contract-hardening`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- objective: Make Direct completion envelopes explicit and make all gateway dispatch receipts expose one complete phase telemetry schema with fail-closed provider diagnostics.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Allowed Files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`

## Required Behavior

1. Direct handoff includes `next_action: edit_canonical_checkout`, `completion_surface: nexus_task_finish`, exact `base_sha`, allowed files, and explicit canonical mutation-lock contract.
2. Direct, Assisted, Isolated, proposal, and fail-closed receipts expose the same telemetry keys: `control_plane_ms`, `route_decision_ms`, `context_build_ms`, `provider_start_ms`, `provider_time_ms`, `patch_validation_ms`, `verifier_time_ms`, `commit_time_ms`, `worktree_time_ms`, `cleanup_time_ms`, `total_wall_time_ms`.
3. Provider failures preserve a bounded diagnostic without transmitting extra context or creating lifecycle state.
4. No external provider invocation is added by this card; existing provider behavior remains opt-in and fail-closed.

## Verification Commands

```bash
git diff --check
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-gateway-pycache .venv/bin/python -m pytest -q -p no:cacheprovider tests/nexus/orchestrator/test_unified_mcp_gateway.py
.venv/bin/python scripts/ops/nexus_mcp_gateway.py --self-test
```

## Exit Criteria

- Contract and telemetry tests pass for Direct, Assisted, Isolated, proposal, and failure paths.
- Scoped commit and Direct receipt exist.
- External DevSpace and GPT connector remain untouched.

## Completion Evidence

- Runtime commit: `727c8b592edabe9aebbab5fca97cbd4e85691262`
- Direct receipt: `ffa75a97df0bf08b02226c92ef94cd42de1b309ece98ace7a8743dd83fed011a`
- Verification: 12 gateway tests passed; gateway self-test passed; `git diff --check` passed.
