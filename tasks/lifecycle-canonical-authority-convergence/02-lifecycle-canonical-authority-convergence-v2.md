# Task Card 02: Lifecycle Canonical Authority Convergence V2

## Identity

- task_id: `lifecycle-canonical-authority-convergence-v2`
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

Form one durable, auditable lifecycle Candidate from the canonical Controller and state root after the authority, compact status, verifier-manifest, worker-environment, and nested-state inventory hardening. The daily source checkout remains untouched.

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
- `tasks/lifecycle-canonical-authority-convergence/02-lifecycle-canonical-authority-convergence-v2.md`

## Forbidden scope

No mutation of `/Users/jameschen/Workspace/nexus`; no direct lifecycle JSON edits; no changes to `AGENTS.md`, `CLAUDE.md`, `MUSE_PROTO.md`, or GitNexus directives; no Worker approval, integration, push, branch/ref deletion, or production claim.

## Verification commands

```bash
/Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q -p no:cacheprovider tests/services/test_workspace_manager.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/executors/test_cli_worker.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_task_contract.py tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_mcp.py
/Users/jameschen/Workspace/nexus/.venv/bin/python -m compileall -q nexus/orchestrator/self_hosted_task_service.py nexus/orchestrator/candidate_verifier.py nexus/executors/cli_worker.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
```

## Evidence required

Record Controller/Target revisions, task-card and contract hashes, verifier-manifest and receipt hashes, Candidate commit/tree/ref, exact approval binding, integration receipt, workspace inventory/plan hashes, and canonical-root cutover rehearsal evidence. All lifecycle state changes must use the formal service/CLI.

## Exit criteria

The Candidate reaches `PENDING_HUMAN_APPROVAL`, exact approval succeeds, integration into `nexus/integration/main` succeeds, the superseded failed attempt retains its salvage ref, and workspace/canonical-root convergence is applied only from an exact plan hash or remains explicitly fail-closed with retained blockers.

## Residual debt

Dirty/unmapped workspaces and the dirty daily source checkout remain retained unless a formal exact-boundary plan proves safe cleanup.

## Block classification

- `RECOVERABLE_BLOCK`: transient provider, permission, or test condition with state preserved.
- `HARD_BLOCK`: authority conflict, task-card drift, unsafe root mutation, missing Candidate proof, or failed exact integration binding.
