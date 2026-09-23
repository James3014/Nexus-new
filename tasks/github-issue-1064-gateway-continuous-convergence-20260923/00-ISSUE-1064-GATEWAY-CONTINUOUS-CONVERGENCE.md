# Task Card: ISSUE-1064-GATEWAY-CONTINUOUS-CONVERGENCE

artifact_authority: current
task_id: `ISSUE-1064-GATEWAY-CONTINUOUS-CONVERGENCE`
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

Implement Issue #1064 as the smallest policy/control-plane seam for level-triggered desired-vs-loaded Gateway convergence. Freeze G0 as POLICY_CONTRACT_GAP + THIN_CALLER_GAP. Preserve #946 observability-only, #807 readiness ownership, #526 as sole Gateway replacement-effect owner, explicit PINNED behavior, explicit TRACK_ACCEPTED_MAIN behavior, no-blind-resend, pre-effect coalescing, in-flight reconciliation-before-successor, fail-closed UNKNOWN/unsafe state, and exact postflight. Do not add a daemon, process manager, effect ledger, second desired-state SSOT, route authority, Workforce authority, merge/release/production authority, or host effect in this source task.

## Allowed files

- `nexus/contracts/gateway_convergence.py`
- `nexus/orchestrator/gateway_convergence.py`
- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/contracts/test_gateway_convergence.py`
- `tests/nexus/orchestrator/test_gateway_convergence.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `docs/specs/NEXUS_GATEWAY_CONVERGENCE_001.md`

## Verification commands

```bash
python -m pytest -q tests/contracts/test_gateway_convergence.py
python -m pytest -q tests/nexus/orchestrator/test_gateway_convergence.py
python -m pytest -q tests/nexus/orchestrator/test_unified_mcp_gateway.py -k gateway_convergence
python -m py_compile nexus/contracts/gateway_convergence.py nexus/orchestrator/gateway_convergence.py
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
