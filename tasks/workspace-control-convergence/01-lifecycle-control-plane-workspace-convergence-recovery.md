# Task Card 01: Lifecycle Control Plane Workspace Convergence Recovery

## Identity
- task_id: `lifecycle-control-plane-workspace-convergence-recovery`
- campaign_id: `workspace-control-convergence`
- artifact_authority: current
- status: SUPERSEDED
- superseded_by: `workspace-convergence-core-primitives`, `workspace-convergence-service-orchestration`, `workspace-convergence-cli-surface`
- owner: James Chen
- supersedes: `lifecycle-control-plane-workspace-convergence`
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective
Recover the owner-approved canonical-workspace convergence and reusable execution-slot implementation after the Agy transport failure. Start from the clean current Controller, inspect the protected salvage commit as evidence, reconstruct only defensible changes, run all mandatory verification, and form one scoped Candidate commit.

## Recovery evidence
- Original card: `tasks/workspace-control-convergence/00-lifecycle-control-plane-workspace-convergence.md`.
- Original lifecycle task: `lifecycle-control-plane-workspace-convergence`.
- Original attempt ID: `2e73a792d9144335999fea648e038479`.
- Original disposition: `FINAL_BLOCK`, `execution_outcome=FAILED`, no Candidate, no verification receipt.
- Provider evidence: Agy `gemini-3.6-flash-high`, three account-pool subprocesses, all exit 1 after orphaned `/usr/bin/security -i` credential pipes; transport failure, not a verified implementation failure.
- Protected salvage commit: `3594db42873a0a8248203578372c6ba9410c83db`.
- Protected salvage ref: `refs/nexus-salvage/worktree/lifecycle-control-plane-workspace-convergence-2e73a792d9144335999fea648e038479`.
- Salvage parent: `d36edb111cbd6303ec3e2da091e18e05490d4736`.
- Salvage scope: seven allowed files, 1,130 insertions and 1 deletion, no tracked-file deletions. `git diff --check` reports trailing blank-line errors, so the salvage is unverified and must not be promoted directly.

## Required recovery behavior
1. Read the original card as the complete product and authority contract. Preserve every required behavior, forbidden scope, proof case, evidence requirement, and claim ceiling unless this card explicitly narrows it.
2. Inspect the salvage commit with read-only Git commands. Do not cherry-pick, merge, or promote it wholesale.
3. Reconstruct the implementation from the clean Controller using TDD. Reuse salvage code only after reviewing it against current code, the original card, and existing lifecycle authority.
4. Correct all `git diff --check` failures and any defects found by tests or code review.
5. Keep the implementation within existing `WorktreeManager`, `SelfHostedTaskService`, self-hosted action, and CLI authority. Do not create a parallel lifecycle, cleanup path, router, state store, or integration authority.
6. The live dirty legacy root and existing linked worktrees remain read-only. All apply-path tests must use temporary repositories or fixtures.
7. Produce one scoped commit and allow Nexus to capture and independently verify it as a Candidate.

## Allowed files
- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`
- `tests/engine/test_self_hosted_cli.py`

## Forbidden scope
- No changes outside the eight allowed files.
- No edits to either Task Card or Campaign Index from the Target.
- No changes to provider adapters, Agy account-pool implementation, model workforce policy, Candidate verifier, governed integration authority, MCP transport, Planner, Router, Receipt schema, or task store.
- No mutation of `/Users/jameschen/Workspace/nexus`.
- No live worktree removal, branch deletion, tag deletion, Candidate-ref deletion, salvage-ref deletion, reset, stash, clean, checkout switch, merge, rebase, integration, or push.
- No direct cherry-pick or merge of salvage commit `3594db42873a0a8248203578372c6ba9410c83db`.
- No new report, ADR, plan, runbook, or parallel persistent artifact.

## Mandatory review handles
- `WorkspaceInventory`
- `WorkspaceConvergencePlan`
- `ReusableExecutionSlot`
- `inventory_hash` or equivalent stable plan binding
- `cleanup_terminal_target`
- `create_salvage_snapshot`
- controller revision drift
- active/retained Target classification
- unique unprotected commit blocker
- idempotent same-base slot preparation

If the salvage uses different names, preserve behavior rather than names unless the names conflict with current conventions.

## Required RED/proof cases
1. Dirty legacy root is inventoried and excluded from apply.
2. Active Target blocks convergence and slot reuse.
3. RETAINED_FOR_REVIEW or FINAL_BLOCK evidence cannot be orphaned.
4. Clean redundant terminal Target can be planned for release only through existing cleanup authority.
5. Unique commit without Candidate/salvage protection is blocked.
6. Controller revision or plan-hash drift fails before mutation.
7. Dirty reusable slot remains untouched and reports a blocker.
8. Same-base slot preparation is idempotent.
9. Different-base slot reuse requires verified prior release.
10. CLI defaults to dry-run and emits machine-readable controller revision, inventory/plan hash, affected paths, blocker codes, deletion count, and next gate.
11. No live repository/worktree path is mutated by tests.
12. All salvage trailing-whitespace/blank-line defects are absent from the Candidate.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_workflow_repair.py tests/engine/test_self_hosted_cli.py`
- `python3 -m compileall -q nexus/orchestrator/worktree_manager.py nexus/orchestrator/self_hosted_task_service.py scripts/engine/commands/self_hosted_actions.py scripts/engine/nexus_cli.py`
- `git diff --check`
- `git diff --name-status --diff-filter=D`
- `git diff --cached --name-status --diff-filter=D`
- `git diff --stat`
- `git diff --cached --stat`

## Evidence required
- Candidate commit SHA and parent SHA.
- Exact changed-file list limited to the eight allowed files.
- Exact verifier outputs.
- Controller unchanged evidence.
- Candidate state hash and verified receipt hash.
- Comparison summary against salvage commit: retained behaviors, rejected unsafe parts, and repaired defects.
- Explicit confirmation that the dirty legacy root, live worktree inventory, branches, tags, Candidate refs, and salvage refs were not mutated.
- Zero tracked-file deletions.

## Exit criteria
- One scoped Candidate commit from the clean Controller base.
- All original-card behavior is implemented or the task returns `HARD_BLOCK` with the exact authority/architecture conflict.
- All mandatory verification commands pass.
- No provider or worker output is treated as independent verification.
- AUTO_CHAIN remains false; no approval, integration, live convergence apply, push, or cleanup of historical evidence occurs.

## Block classification
- `RECOVERABLE_BLOCK`: transient Codex CLI/provider failure or verifier environment problem that preserves the Target and evidence.
- `HARD_BLOCK`: original-card authority conflict, unsafe salvage behavior that cannot be repaired in allowed scope, need to modify forbidden files, inability to preserve evidence, or requirement to create a new authority path.

## Maximum claim
`WORKSPACE_CONVERGENCE_AND_REUSABLE_SLOT_RECOVERY_CANDIDATE_READY`

## Next gate
Independent Candidate review only.
