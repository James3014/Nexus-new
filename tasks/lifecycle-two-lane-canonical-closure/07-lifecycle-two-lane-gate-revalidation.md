# Task Card 07: Lifecycle Two-lane Gate Revalidation

## Identity

- task_id: `lifecycle-two-lane-gate-revalidation`
- campaign_id: `lifecycle-two-lane-canonical-closure`
- artifact_authority: current
- status: IN_PROGRESS
- owner: James Chen
- objective: Revalidate the full owner-authorized two-lane lifecycle plan against real Direct commits, real isolated Target success/cleanup, owner-finish archive closure, fault/retry actions, SLO telemetry, and external workspace disposition.
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Inputs and dependencies

- `tasks/lifecycle-two-lane-canonical-closure/INDEX.md`
- P0-P6 cards and commits listed in that index
- `/Users/jameschen/.codex/attachments/b09590a6-4abf-4c88-9ea6-656d2155800a/pasted-text-1.txt`
- Current canonical root, lifecycle state root, Target root, external MCP checkout, and salvage directory

## Allowed files

- `tasks/lifecycle-two-lane-canonical-closure/INDEX.md`
- `tasks/lifecycle-two-lane-canonical-closure/07-lifecycle-two-lane-gate-revalidation.md`
- `nexus/orchestrator/self_hosted_task_service.py`
- `nexus/orchestrator/worktree_manager.py`
- `nexus/orchestrator/self_hosted_mcp.py`
- `scripts/engine/commands/self_hosted_actions.py`
- `scripts/engine/nexus_cli.py`
- `tests/nexus/orchestrator/test_self_hosted_task_service.py`
- `tests/nexus/orchestrator/test_self_hosted_mcp.py`
- `tests/engine/test_self_hosted_cli.py`

## Required behavior

1. Direct lane rejects lockfiles, generated/large changes, authority-sensitive flags, delegated workers, dirty roots, wrong branch, and concurrent mutation tasks; eligible Direct completion has an explicit preflight, scoped verification, staged-diff gate, and commit-bound receipt without Candidate/Target creation.
2. Isolated lane rejects the disabled root, uses only `/Users/jameschen/Workspace/nexus-runtime-targets`, serializes one active slot, and preserves lazy read-only behavior.
3. `owner_finish` verifies binding, integrates, and archives the terminal receipt; mismatch or branch/verifier drift leaves approval and integration unmodified.
4. Integration failures expose a callable same-task integration retry; verified-uncommitted and dirty-retained cases expose one precise next action; duplicate Task Card hashes return the existing task and retry action without a second logical task.
5. Receipts expose separate provider, verifier, worktree, commit/hook, cleanup, wall, and overhead timing fields sufficient to calculate p95 SLOs.

## Verification commands

```bash
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_task_service.py -k 'revalidation or direct or owner_finish or retry or fault'
uv run pytest -q tests/nexus/orchestrator/test_self_hosted_mcp.py tests/engine/test_self_hosted_cli.py
git status --short --branch
git worktree list --porcelain
```

## Gate matrix

- 15 real Direct Lane commit cycles: `new_worktree_count=0`, no lifecycle Candidate, clean after each cycle.
- 10 real Isolated Target success cycles: one serial reusable slot, terminal cleanup, no active Target afterward.
- 5 fault/retry cycles: timeout, provider error, verifier failure, commit failure, integration failure; same task ID and one executable next action.
- SLO p95: read <300ms, Direct overhead <1s, warm Target prepare/release <5s.
- P0 external disposition: disabled roots absent, MCP checkout clean, residue path/hash recorded, parent workspace guard present.

## Forbidden scope

No direct lifecycle JSON edits, no worker approval/integration, no push, no protected history rewrite, no deletion of branches/refs, no GitNexus forced directives, and no deletion of salvaged external residue.

## Exit criteria and residual debt

Complete only when every matrix row and SLO gate has physical receipt evidence, the canonical root and external MCP checkout are clean, no actionable orphan lacks owner disposition, and this card has a scoped commit. If a gate cannot be proven, leave the card `RECOVERABLE_BLOCK` or `HARD_BLOCK` with the exact missing evidence; do not downgrade the objective.
