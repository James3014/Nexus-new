# Task Card 03: Workspace Convergence Service Orchestration

## Identity
- task_id: `workspace-convergence-service-orchestration`
- campaign_id: `workspace-control-convergence`
- artifact_authority: current
- status: INTEGRATED_WITH_OWNER_REVIEW
- owner: James Chen
- depends_on: `workspace-convergence-core-primitives` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective
Integrate the verified core inventory, convergence-plan, and reusable-slot primitives into `SelfHostedTaskService` without adding a parallel authority or performing live convergence.

## Required behavior
1. Add service operations for read-only inventory, dry-run plan, and reusable-slot readiness/preparation.
2. Bind every plan/apply request to exact Controller revision and stable inventory/plan hash; drift fails before mutation.
3. Derive active, retained, terminal, Candidate, and salvage evidence from existing lifecycle state.
4. Any apply seam delegates exclusively to existing `WorktreeManager` salvage/cleanup authority.
5. `/Users/jameschen/Workspace/nexus` is always excluded from apply.
6. Defaults are dry-run, zero deletions, no approval/integration/push.
7. Machine-readable results include affected paths, blocker codes, deletion count, Controller revision, plan hash, and next gate.

## Allowed files
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`

## Forbidden scope
No other files; no CLI/MCP/provider/account-pool/Candidate/verifier/integration/Router/Planner/Receipt changes; no live workspace mutation; no branch/tag/ref/tracked-file deletion.

## Required proof
- active/retained lifecycle evidence blocks release and reuse;
- stale Controller revision or plan hash fails closed;
- unknown state remains non-releasable;
- temporary-fixture safe release delegates to existing cleanup authority;
- repeated slot preparation is idempotent;
- live legacy root is excluded.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_workflow_repair.py`
- `python3 -m compileall -q nexus/orchestrator/self_hosted_task_service.py`
- `git diff --check`
- `git diff --name-status --diff-filter=D`
- `git diff --cached --name-status --diff-filter=D`
- `git diff --stat`
- `git diff --cached --stat`

## Exit criteria
One verified three-file Candidate; zero deletions; Controller unchanged; no auto-chain.

## Maximum claim
`WORKSPACE_CONVERGENCE_SERVICE_ORCHESTRATION_CANDIDATE_READY`

## Next gate
Owner-integrated at `eece9edd9`; service/workflow verifier suite passed 109 tests. CLI surface remains the next bounded consumer.
