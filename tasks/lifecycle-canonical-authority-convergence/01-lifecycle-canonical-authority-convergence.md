# Task Card 01: Lifecycle Canonical Authority Convergence

## Identity

- task_id: `lifecycle-canonical-authority-convergence`
- campaign_id: `lifecycle-canonical-authority-convergence`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Converge the self-hosted lifecycle onto one durable Controller/state authority, fail closed before production-bound promotion when authority is ephemeral, expose compact lock-free status reads, deduplicate verifier manifests, isolate ambient worker environment, and inventory nested canonical state receipts without mutating the dirty daily source checkout.

## Allowed files

- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `nexus/orchestrator/candidate_verifier.py`
- `nexus/executors/cli_worker.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_candidate_verifier.py`
- `tests/nexus/executors/test_cli_worker.py`
- `tasks/lifecycle-canonical-authority-convergence/INDEX.md`
- `tasks/lifecycle-canonical-authority-convergence/01-lifecycle-canonical-authority-convergence.md`

## Forbidden scope

Do not mutate `/Users/jameschen/Workspace/nexus`; do not edit `AGENTS.md`, `CLAUDE.md`, `MUSE_PROTO.md`, or GitNexus directives; do not directly edit lifecycle JSON; do not approve, integrate, push, delete branches/refs, or claim production readiness from the Worker; do not run GitNexus; do not broaden the verifier manifest beyond the listed commands.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p6-pycache /Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/services/test_workspace_manager.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/executors/test_cli_worker.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_task_contract.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_mcp.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX=/tmp/nexus-p6-pycache /Users/jameschen/Workspace/nexus/.venv/bin/python -m compileall -q nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/candidate_verifier.py nexus/executors/cli_worker.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
```

## Evidence required

Record the exact Controller revision, Target base revision, contract hash, task-card hash, deduplicated verifier manifest hash, verified receipt hash, Candidate commit/tree/ref, approval binding, integration receipt, workspace inventory/plan hashes, and canonical-root cutover rehearsal result. Candidate, approval, and integration state must be produced by the formal lifecycle API/CLI.

## Exit criteria

The Candidate is `PENDING_HUMAN_APPROVAL` before approval, exact approval succeeds, integration into `nexus/integration/main` succeeds with a fresh integration receipt, old superseded lifecycle evidence is closed through the formal service, and workspace convergence/canonical cutover is either applied from an exact plan hash or fail-closed with named retained blockers.

## Residual debt

Dirty or unmapped workspaces and the dirty daily source checkout remain retained unless a formal exact-boundary plan proves safe cleanup. No legacy receipt is deleted merely because a successor exists; every closure retains a salvage or historical reference.

## Block classification

- `RECOVERABLE_BLOCK`: transient provider, test-permission, or process condition with state preserved.
- `HARD_BLOCK`: controller/state authority conflict, task-card hash drift, unsafe root mutation, missing durable Candidate evidence, or failed exact integration binding.
