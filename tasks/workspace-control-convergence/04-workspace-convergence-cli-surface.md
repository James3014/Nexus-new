# Task Card 04: Workspace Convergence CLI Surface

## Identity
- task_id: `workspace-convergence-cli-surface`
- campaign_id: `workspace-control-convergence`
- artifact_authority: current
- status: INTEGRATED_WITH_OWNER_REVIEW
- owner: James Chen
- depends_on: `workspace-convergence-service-orchestration` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective
Expose the integrated service operations through the existing self-hosted action and CLI surfaces with machine-readable, dry-run-first behavior.

## Required behavior
1. Extend existing self-hosted commands/actions for workspace inventory, convergence planning, and reusable-slot readiness/preparation.
2. Default convergence to dry-run; explicit apply requires exact Controller revision and plan hash.
3. Output Controller revision, inventory/plan hash, affected paths, blocker codes, deletion count, action state, and next gate.
4. Preserve existing exception translation and action-envelope conventions.
5. No new executable, MCP authority, state store, router, verifier, integration path, or production claim.

## Allowed files
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/engine/test_self_hosted_cli.py`

## Forbidden scope
No other files; no live workspace mutation; no branch/tag/ref/tracked-file deletion; no approval/integration/push.

## Required proof
- inventory command is read-only and machine-readable;
- convergence command defaults to dry-run;
- missing/stale revision or plan hash fails closed;
- reusable-slot command reports blockers without force reuse;
- CLI tests use temporary fixtures only.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/engine/test_self_hosted_cli.py`
- `python3 -m compileall -q scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py`
- `git diff --check`
- `git diff --name-status --diff-filter=D`
- `git diff --cached --name-status --diff-filter=D`
- `git diff --stat`
- `git diff --cached --stat`

## Exit criteria
One verified three-file Candidate; zero deletions; Controller unchanged; no auto-chain.

## Maximum claim
`WORKSPACE_CONVERGENCE_CLI_SURFACE_CANDIDATE_READY`

## Next gate
Owner-integrated at `72dee3d5d`; self-hosted CLI verifier suite passed 28 tests. P6 canonical-root cutover remains separately gated.
