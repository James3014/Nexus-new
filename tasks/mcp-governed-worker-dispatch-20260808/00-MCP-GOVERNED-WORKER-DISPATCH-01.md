# Task Card: MCP-GOVERNED-WORKER-DISPATCH-01

artifact_authority: current
task_id: `MCP-GOVERNED-WORKER-DISPATCH-01`
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

Expose the existing governed SelfHostedTaskService worker submission capability through the canonical MCP Gateway so ChatGPT can submit one Task-Card-bound delegated source-code implementation to the existing ISOLATED_TARGET lifecycle using an admitted worker such as agy. Add only a thin public submission seam; do not create a new router, planner, worker engine, lifecycle, or direct-apply path. CapabilityPlanner/HybridRouteDecision remain route authority. Do not activate or reuse _apply_assisted_patch for delegated mutation: delegated workers must never be laundered into DIRECT_CANONICAL/primary_agent. Preserve existing nexus_task_run product-runtime semantics and existing nexus_assist_submit candidate-only semantics. The new/extended public surface must bind task_id, current controller revision, Task Card identity, bounded allowed files/verifiers, and explicit worker provider; it must delegate to the existing SelfHostedTaskService governed submission path and yield existing task/status/wait/Candidate lifecycle evidence. Agy must use the existing registered agy worker adapter/default gemini-3.6-flash-high policy rather than introducing model-selection authority. AUTO_CHAIN remains false. No approval, integration, push, cleanup, production/public claim, or successor execution. If accomplishing this requires modifying SelfHostedTaskService, WorkerRegistry, CapabilityPlanner, workforce policy, or more than the allowed files, stop with HARD_BLOCK and report the exact missing seam.

## Allowed files

- `nexus/orchestrator/unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway.py`
- `tests/nexus/orchestrator/test_unified_mcp_gateway_http.py`

## Verification commands

```bash
python3 -m pytest tests/nexus/orchestrator/test_unified_mcp_gateway.py tests/nexus/orchestrator/test_unified_mcp_gateway_http.py -q
git diff --check
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
