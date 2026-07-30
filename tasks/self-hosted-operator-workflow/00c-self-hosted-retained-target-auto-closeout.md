# Task Card 00c: Self-hosted Retained Target Auto Closeout

## Identity
- task_id: `self-hosted-retained-target-auto-closeout`
- campaign_id: `self-hosted-operator-workflow`
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
- maximum_claim: `SELF_HOSTED_RETAINED_TARGET_AUTO_CLOSEOUT_CANDIDATE_READY`

## Objective
Make terminal `RETAINED_FOR_REVIEW` tasks release their registered Target automatically and reversibly: preserve any non-candidate work under a durable salvage ref, then remove the worktree while keeping the task retained for explicit review or supersession.

## Owner decisions
- A retained task does not need an integrated replacement merely to release Target capacity.
- Target cleanup is not supersession, approval, integration, promotion, rejection, or evidence deletion.
- `AUTO_CHAIN=false` remains authoritative; successful cleanup must not start another task.
- Dirty or committed non-candidate work must be preserved before Target removal.

## Source and start state
- Controller: `/Users/jameschen/Workspace/nexus-worktrees/integration-main`
- Starting branch: `nexus/integration/main`
- Starting HEAD: governance commit tracking this card
- Reproduced defect: `cleanup_tasks()` unconditionally returns `BLOCKED_BY_UNSAVED_CHANGES` for every `RETAINED_FOR_REVIEW` task and never invokes the existing salvage mechanism.
- Physical example: `self-hosted-verification-entrypoint-final-amendment` has durable salvage `29b9b0d40eb29e0ea590d4cbf05118c7ba3ae43d` but its Target remains registered and consumes serial Target capacity.

## Authority map
- Route and task-selection authority: current Campaign Index and owner decision
- Execution authority: bounded OpenCode Worker
- Verification authority: exact Task Card commands plus independent review
- Receipt authority: canonical self-hosted durable task state and cleanup receipt
- Promotion/integration authority: James / independent reviewer only

## Required observable behavior
1. `cleanup_tasks(task_id=..., dry_run=False)` may process `RETAINED_FOR_REVIEW` when no worker or child process is active.
2. If the Target is dirty and no valid salvage is recorded, create a complete salvage snapshot with `Nexus Salvage Bot`, protect it under the deterministic task/attempt salvage ref, checkpoint the exact commit/ref, and only then remove the Target.
3. If the Target is clean but `HEAD != lease.initial_head`, protect the current HEAD as salvage-only before removal. Reuse an exact existing deterministic salvage ref only when it resolves to the same HEAD.
4. If the Target is clean and `HEAD == lease.initial_head`, remove it without creating a meaningless salvage commit.
5. If valid salvage metadata is already recorded, verify the ref resolves to the recorded commit and Target HEAD before cleanup.
6. After successful cleanup, task status remains `RETAINED_FOR_REVIEW`; `promotion_status=NOT_CREATED`; `salvage_only=true` only when salvage exists; `promotion_eligible=false`; Candidate fields remain absent.
7. Cleanup must record `cleanup_decision=REMOVED` or `ALREADY_REMOVED`, `cleanup_performed`, timestamp, salvage binding when applicable, and a machine-readable reason on failure.
8. Missing/mismatched salvage ref, active process, unregistered non-empty directory, controller path, lease mismatch, or candidate/salvage ambiguity must fail closed and preserve the Target.
9. Dry-run must not commit, create/update refs, checkpoint salvage, remove worktrees, or mutate task state. It must report the planned action.
10. Bulk cleanup must apply the same logic task-by-task without allowing one blocked task to prevent safe cleanup of other terminal tasks.

## Allowed files
- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_worktree_manager.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`

## Forbidden scope
- No changes to Candidate verification, Candidate commit, approval, integration, provider routing, workforce policy, MCP protocol, CLI command surface, Campaign Index, or other Task Cards.
- No automatic supersession, archive, branch deletion, ref deletion, push, reset, stash, clean, or force removal.
- No cleanup of arbitrary unregistered historical Controller snapshots in this card; that requires a separately bounded reconciliation card.
- No downgrade of existing explicit `close_retained_without_candidate(..., superseded_by=...)` authority checks.

## RED witnesses
- retained dirty Target currently remains registered after `cleanup_tasks(..., dry_run=False)`;
- retained clean changed-HEAD Target currently remains registered without a durable binding;
- existing exact salvage ref currently is not discovered when state metadata is absent;
- dry-run currently cannot describe a salvage-and-remove plan because retained tasks are rejected immediately.

## GREEN and regression gates
- dirty retained Target: exact salvage commit/ref created, all tracked and untracked content recoverable, Target removed, task still retained;
- clean changed-HEAD retained Target: HEAD protected as salvage, Target removed, no extra commit required;
- exact pre-existing salvage ref: reused and recorded;
- mismatched existing ref: fail closed, Target preserved;
- active process: zero Git mutation and Target preserved;
- clean initial Target: removed without salvage;
- dry-run: zero state/ref/worktree mutation;
- Candidate cleanup, integrated cleanup, cancellation cleanup, explicit supersession, and recovery surfaces remain green.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_workflow_repair.py`
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_self_hosted_controller.py`
- `python3 -m compileall -q nexus/orchestrator/worktree_manager.py nexus/orchestrator/self_hosted_task_service.py`
- `git diff --check`
- `git diff --name-status --diff-filter=D`
- `git diff --cached --name-status --diff-filter=D`

## Physical evidence required
- exact Candidate SHA/tree/ref/parent and Task Card hash;
- changed files limited to allowed scope;
- RED and GREEN receipts for dirty, clean-changed, pre-existing-ref, active-process, and dry-run cases;
- salvage commit/ref recovery proof including untracked content;
- zero candidate/promotion authority created;
- zero tracked deletions;
- Controller unchanged and Target clean after Candidate formation.

## Independent review
A fresh reviewer must verify safety, reversibility, no authority promotion, no hidden automatic chaining, exact salvage binding, and focused plus regression test results before integration.

## Exit conditions
- PASS: scoped Candidate exists on `refs/heads/nexus/task/self-hosted-retained-target-auto-closeout`, all commands pass, and Candidate stops for review.
- RECOVERABLE_BLOCK: OpenCode transport/quota failure or transient environment issue; preserve the same card and Target.
- HARD_BLOCK: any need to relax salvage/ref validation, delete evidence, broaden to arbitrary Controller snapshots, or change promotion authority.
- Next gate, informational only: integrate this Candidate, run real retained-target cleanup, then resume `self-hosted-verification-entrypoint-opencode-recovery`.
