# Task Card 00d: Self-hosted Terminal Closeout Trigger

## Identity
- task_id: `self-hosted-terminal-closeout-trigger`
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

## Objective
Automatically invoke the already integrated retained-target closeout when a worker failure or timeout transitions a task to `RETAINED_FOR_REVIEW`, so salvage and Target release complete without a separate operator cleanup command.

## Physical defect
- Integrated closeout implementation: `17cf433ef218ea709d2e06ac1d3fcd2e85b90144`.
- Real canary task `self-hosted-verification-entrypoint-opencode-recovery` timed out after 900072 ms and entered `RETAINED_FOR_REVIEW` with `cleanup_decision=BLOCKED_BY_UNSAVED_CHANGES`.
- Manual invocation of existing `cleanup_tasks(..., dry_run=False)` then created salvage `4ac83a4f00ff1690521c97ceaef9c11a344ce0e9`, protected its deterministic ref, and removed the Target.
- Therefore classification/salvage/removal works; terminal transition does not trigger it.

## Required behavior
1. After worker failure, timeout, incomplete execution, or other no-Candidate terminal retention, checkpoint `RETAINED_FOR_REVIEW`, then invoke the existing retained-target cleanup path exactly once.
2. Return/persist the post-closeout state, not the pre-closeout `BLOCKED_BY_UNSAVED_CHANGES` envelope.
3. Dirty Target must be salvaged before removal; clean Target may be removed directly under existing rules.
4. If closeout fails closed, preserve `RETAINED_FOR_REVIEW`, Target, blocker, and evidence; do not mask the original worker failure.
5. Idempotent reconciliation must not create duplicate salvage commits or refs.
6. No auto-supersession, successor start, Candidate formation, approval, integration, push, archive, branch deletion, or ref deletion.

## Allowed files
- `nexus/orchestrator/self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_workflow_repair.py`

## Forbidden scope
- No changes to WorktreeManager primitives, provider adapters, CLI/MCP surfaces, verification entrypoint, Candidate/integration authority, or Campaign Index.
- No force removal or arbitrary historical worktree cleanup.

## RED tests
- timed-out dirty worker currently returns retained state before salvage/removal;
- failed dirty worker currently requires explicit `cleanup_tasks()`;
- closeout exception must preserve original failure and Target.

## Verification commands
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py tests/nexus/orchestrator/test_workflow_repair.py`
- `/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_worktree_manager.py tests/nexus/orchestrator/test_candidate_commit.py tests/nexus/orchestrator/test_candidate_verifier.py`
- `python3 -m compileall -q nexus/orchestrator/self_hosted_task_service.py`
- `git diff --check`

## Exit criteria
- One scoped Candidate; zero deletions and no out-of-scope files.
- Tests prove failure/timeout → retained checkpoint → salvage/protect → Target removal without operator cleanup.
- AUTO_CHAIN remains false and no downstream task starts automatically.

## Maximum claim
SELF_HOSTED_TERMINAL_CLOSEOUT_TRIGGER_CANDIDATE_READY
