# Task Card 02: Workspace Convergence Core Primitives

## Identity
- task_id: `workspace-convergence-core-primitives`
- campaign_id: `workspace-control-convergence`
- artifact_authority: current
- status: INTEGRATED_WITH_OWNER_REVIEW
- owner: James Chen
- supersedes_slice_of: `lifecycle-control-plane-workspace-convergence-recovery`
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Worker ceiling
This is a closed L1 implementation slice suitable for OpenCode MiMo `opencode/mimo-v2.5-free`. The worker has no architecture, integration, cleanup, production, or claim authority.

## Objective
Implement and test only the deterministic Git/worktree primitives required for canonical workspace inventory, fail-closed convergence planning, and one sequential reusable execution slot. Do not expose service or CLI surfaces in this card.

## Inputs
- Original authority: `tasks/workspace-control-convergence/00-lifecycle-control-plane-workspace-convergence.md`.
- Recovery authority and failure evidence: `tasks/workspace-control-convergence/01-lifecycle-control-plane-workspace-convergence-recovery.md`.
- Read-only salvage evidence: commit `3594db42873a0a8248203578372c6ba9410c83db` and ref `refs/nexus-salvage/worktree/lifecycle-control-plane-workspace-convergence-2e73a792d9144335999fea648e038479`.
- Current clean Controller revision is supplied by the lifecycle contract at dispatch.

## Required behavior
1. Add deterministic, machine-serializable worktree inventory primitives under existing `WorktreeManager` authority.
2. Inventory records must expose path, HEAD, branch/detached state, dirty state, Controller identity, registered worktree state, and Controller reachability where physically knowable.
3. Add fail-closed classification/planning primitives covering at least:
   - `KEEP_CONTROLLER`;
   - `KEEP_DIRTY_OR_UNKNOWN`;
   - `KEEP_ACTIVE_OR_RETAINED`;
   - `RELEASABLE_TERMINAL_TARGET`;
   - `RELEASABLE_REDUNDANT_CLEAN`;
   - `BLOCKED_UNPROTECTED_UNIQUE_COMMIT`.
4. Unknown, conflicting, dirty, active, retained, or unprotected unique evidence must never be marked releasable.
5. Produce a stable inventory/plan hash bound to Controller revision and normalized records.
6. Add reusable slot primitives for one deterministic `slot-0` path under the existing runtime-target root. This card may classify readiness and prepare only within temporary test repositories.
7. Same-base preparation must be idempotent. Different-base reuse must fail unless the prior slot is physically absent or proven clean/releasable through existing authority.
8. Reuse existing salvage and terminal cleanup primitives. Do not add raw branch/ref deletion, reset, stash, clean, or force removal.
9. No production/live worktree apply in this card. Tests must use temporary repositories only.
10. Inspect salvage read-only; do not cherry-pick or merge it wholesale. Retain only behavior that survives current-code review and tests.

## Allowed files
- `nexus/orchestrator/worktree_manager.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`

## Forbidden scope
- No other files.
- No service, CLI, MCP, provider, account-pool, Candidate, verifier, integration, Router, Planner, Receipt, Task Card, or documentation changes.
- No mutation of `/Users/jameschen/Workspace/nexus` or existing linked worktrees.
- No branch, tag, Candidate-ref, salvage-ref, or tracked-file deletion.
- No live convergence apply.

## Required RED/proof cases
1. Controller is always kept.
2. Dirty or unknown worktree is kept.
3. Active or retained Target is kept.
4. Unique unprotected commit is blocked.
5. Clean redundant terminal Target can be classified releasable without being removed.
6. Inventory/plan hash changes on Controller or inventory drift.
7. Dirty slot fails closed and remains untouched.
8. Same-base slot readiness/preparation is idempotent.
9. Different-base slot reuse blocks until verified release.
10. Temporary-fixture apply delegation never bypasses existing cleanup authority.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py`
- `python3 -m compileall -q nexus/orchestrator/worktree_manager.py`
- `git diff --check`
- `git diff --name-status --diff-filter=D`
- `git diff --cached --name-status --diff-filter=D`
- `git diff --stat`
- `git diff --cached --stat`

## Evidence required
- Candidate commit SHA and parent.
- Exact two-file changed list.
- Exact verifier output.
- Controller unchanged evidence.
- Candidate state hash and verified receipt hash.
- Zero tracked-file deletions.
- Explicit statement that salvage was inspected read-only and live worktrees were not mutated.

## Exit criteria
- One scoped Candidate limited to the two allowed files.
- All required tests and static checks pass.
- Inventory, plan, and slot primitives fail closed and remain non-destructive.
- No downstream card starts automatically.

## Block classification
- `RECOVERABLE_BLOCK`: transient OpenCode transport/provider or verifier environment failure.
- `HARD_BLOCK`: behavior requires changes outside allowed files, new authority, destructive Git operations, or cannot preserve dirty/unique evidence.

## Maximum claim
`WORKSPACE_CONVERGENCE_CORE_PRIMITIVES_CANDIDATE_READY`

## Next gate
Historical worker Candidate state remains `RETAINED_FOR_REVIEW`; the equivalent implementation was owner-integrated at `74808adb6` after the commit-aware contract fix, with 66 WorktreeManager tests passing. No downstream card may infer formal Candidate promotion from this owner integration.
