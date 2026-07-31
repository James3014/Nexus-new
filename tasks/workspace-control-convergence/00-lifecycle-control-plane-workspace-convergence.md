# Task Card 00: Lifecycle Control Plane Workspace Convergence

## Identity
- task_id: `lifecycle-control-plane-workspace-convergence`
- campaign_id: `workspace-control-convergence`
- artifact_authority: current
- status: READY
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective
Add a governed, fail-closed canonical-workspace convergence surface and one reusable execution slot to the existing Nexus self-hosted lifecycle control plane. The Candidate must make workspace state classifiable, preserve all unique or dirty evidence, and permit sequential reuse only after the prior lease has reached a verified releasable terminal state.

## Verified start state
- Controller repository: `/Users/jameschen/Workspace/nexus-worktrees/integration-main`
- Controller branch before this card commit: `nexus/integration/main`
- Controller implementation base before this card commit: `0632fc814b46e7eb7f4fe867c07e315d8b2513f7`
- Dirty legacy root: `/Users/jameschen/Workspace/nexus`, branch `feature/full-capability-closure-20260718`, HEAD `a2185edb0e67e3fc9d6ed7169593d9d80bb1c03a`
- The legacy root had 117 dirty/untracked status entries at audit time and must not be reset, stashed, cleaned, overwritten, committed, or switched by this Candidate task.
- Linked worktree count at audit time: 26.
- Lifecycle states at audit time: 69 total; 26 INTEGRATED, 34 SUPERSEDED, 3 RETAINED_FOR_REVIEW, 6 FINAL_BLOCK; zero active nonterminal tasks.
- The OpenCode process that held the legacy root was terminated normally before this card was created.

## Settled authority decisions
1. `nexus/integration/main` remains the sole Controller and integration authority.
2. This task changes control-plane code and tests only. It must not perform the live destructive convergence of existing worktrees while building the Candidate.
3. The reusable slot is sequential, not parallel. At most one active Target lease may occupy it.
4. Dirty state, unique commits, Candidate refs, salvage refs, retained evidence, unresolved terminal tasks, and unknown worktree ownership all fail closed.
5. Existing `WorktreeManager`, `SelfHostedTaskService`, Candidate, verifier, approval, and governed integration authorities remain authoritative. Do not create a parallel lifecycle, router, task store, or integration path.
6. The worker may create one scoped commit in its isolated Target. It may not approve, integrate, push, switch the legacy root, remove historical worktrees, or delete branches/tags/refs.

## Required behavior

### A. Canonical workspace inventory and classification
1. Add one deterministic service-level inventory operation that reports:
   - controller root, branch, HEAD, and dirty state;
   - legacy/canonical-root candidate identity and dirty state;
   - linked worktree path, HEAD, branch or detached state;
   - whether a worktree is the Controller, an active Target, retained evidence, terminal/releasable, dirty, clean, missing, or unknown;
   - whether its HEAD is reachable from the Controller;
   - whether protected Candidate/salvage refs bind relevant evidence when lifecycle state requires them.
2. Classification must be evidence-bounded and stable for machine consumption. Unknown or conflicting evidence must be explicit and must not be classified as safe to release.
3. Inventory is read-only and must not mutate Git state.

### B. Fail-closed convergence plan/apply seam
1. Add a dry-run convergence plan that groups linked worktrees into at least:
   - `KEEP_CONTROLLER`;
   - `KEEP_DIRTY_OR_UNKNOWN`;
   - `KEEP_ACTIVE_OR_RETAINED`;
   - `RELEASABLE_TERMINAL_TARGET`;
   - `RELEASABLE_REDUNDANT_CLEAN`;
   - `BLOCKED_UNPROTECTED_UNIQUE_COMMIT`.
2. Any apply seam must delegate to existing lifecycle cleanup/salvage primitives. Do not implement raw `git worktree remove`, branch deletion, ref deletion, reset, stash, or clean as an alternative authority.
3. Apply must require exact expected Controller revision and an unchanged inventory/plan hash. Drift must fail closed before mutation.
4. Dirty or unique evidence must be salvaged and protected by existing mechanisms before any eligible Target release.
5. The legacy root `/Users/jameschen/Workspace/nexus` is never an apply target in this card.
6. This Candidate may test apply behavior only in temporary repositories/fixtures. Do not apply convergence to the live 26-worktree inventory.

### C. Reusable execution slot
1. Add a deterministic reusable slot identity under the existing runtime-target root, scoped to one campaign and one slot index (`slot-0`).
2. Reuse is allowed only when:
   - no active/nonterminal lifecycle task owns the slot;
   - the prior Target is absent or verified clean and releasable through existing cleanup authority;
   - no retained, Candidate, salvage, or blocker evidence would be orphaned;
   - the requested target base revision resolves exactly;
   - Controller revision and task-card binding are current.
3. If any prerequisite fails, preserve the existing Target and return an explicit blocker. Never force reuse.
4. Sequential reuse must not create an unbounded new per-attempt worktree path. Retries preserve stable task identity and use a new attempt/provider identity only.
5. Slot preparation must be idempotent. Repeating a successful prepare for the same exact base must not create duplicate branches, refs, or worktrees.

### D. Operator surface
1. Extend the existing self-hosted CLI/action surface rather than adding a separate executable.
2. Provide machine-readable status for inventory, convergence dry-run, and reusable-slot readiness/preparation.
3. Default convergence behavior is dry-run. Any apply action must be explicit and must preserve existing human approval boundaries.
4. Output must include controller revision, inventory/plan hash, affected paths, blocker codes, deletion count, and next allowed gate.

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
- No changes to provider adapters, account-pool policy, model workforce policy, Candidate verifier, governed integration authority, MCP transport, Planner, Router, Receipt schema, or task-card files.
- No mutation of `/Users/jameschen/Workspace/nexus`.
- No live worktree removal, branch deletion, tag deletion, Candidate-ref deletion, salvage-ref deletion, reset, stash, clean, checkout switch, merge, rebase, integration, or push.
- No new report, ADR, plan, runbook, or parallel state store.
- No production-ready or public-claim assertion.

## Required RED/proof cases
1. Dirty legacy root is inventoried and excluded from apply.
2. Active Target blocks convergence and slot reuse.
3. RETAINED_FOR_REVIEW or FINAL_BLOCK with required evidence blocks release unless existing cleanup authority proves a safe release path.
4. Clean redundant terminal Target can be planned for release.
5. Unique commit without Candidate/salvage protection is blocked.
6. Controller revision drift invalidates an earlier plan hash.
7. Dirty reusable slot fails closed and remains untouched.
8. Same-base slot preparation is idempotent.
9. Different-base slot reuse occurs only after verified prior release.
10. No test path relies on deleting a tracked branch/ref or mutating the live workspace inventory.

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
- Exact changed-file list proving scope is limited to the eight allowed files.
- Exact verifier commands and outputs.
- Controller unchanged evidence.
- Candidate state hash and verified Candidate receipt hash.
- Inventory/plan schema example from a temporary repository fixture.
- Explicit confirmation that the live legacy root and live linked worktrees were not mutated.
- Deletion audit showing zero tracked-file deletions.

## Exit criteria
- One scoped Candidate commit, zero out-of-scope files, and zero tracked-file deletions.
- Inventory is deterministic and read-only.
- Convergence defaults to dry-run and fails closed on drift, dirty state, active ownership, retained evidence, unknown ownership, or unprotected unique commits.
- Reusable slot is sequential, idempotent, bounded, and cannot orphan lifecycle evidence.
- All mandatory verification commands pass.
- AUTO_CHAIN remains false; no downstream task starts automatically.

## Block classification
- `RECOVERABLE_BLOCK`: provider/account quota, transient CLI failure, temporary process ownership, or a verifier environment issue that does not invalidate the card.
- `HARD_BLOCK`: architecture/authority conflict, need to mutate forbidden paths, inability to preserve dirty or unique evidence, requirement to delete branches/refs, controller drift that cannot be reconciled, or any need to bypass existing lifecycle cleanup authority.

## Maximum claim
`WORKSPACE_CONVERGENCE_AND_REUSABLE_SLOT_CANDIDATE_READY`

## Next gate
Independent Candidate review only. Integration and live convergence apply are not authorized by this card.
