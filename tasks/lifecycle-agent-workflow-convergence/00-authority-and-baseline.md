# Task Card: lifecycle-workflow-p0-authority-baseline

artifact_authority: current
owner: James Chen
status: COMPLETED
task_id: lifecycle-workflow-p0-authority-baseline
read_only: false
audit_only: false
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Create the executable campaign authority and durable lifecycle contract for
three lanes, Task/Attempt/Action identity, Candidate separation, recovery, and
cleanup. Do not change runtime code in this card.

## Inputs

- The owner-supplied implementation plan at the source specification path in INDEX.md.
- Current canonical HEAD and the root AGENTS.md.
- Current single-MCP campaign and active campaign indexes.

## Allowed files

- `tasks/lifecycle-agent-workflow-convergence/INDEX.md`
- `tasks/lifecycle-agent-workflow-convergence/00-authority-and-baseline.md`
- `docs/arch/LIFECYCLE_AGENT_WORKFLOW_CONTRACT.md`

## Forbidden scope

- No runtime Python changes.
- No worktree, branch, ref, or cleanup mutation.
- No edit to workforce policy, CapabilityPlanner authority, or active unrelated campaigns.
- No external installation or machine-local Skill edits.

## Contract requirements

- Direct lane is canonical and Target-free.
- Assisted lane produces a bounded candidate and requires verification before apply/commit.
- Isolated lane owns a governed Target and Candidate binding.
- `task_id` survives retry; `attempt_id` changes per attempt; every mutation has `action_id` and `idempotency_key`.
- Candidate, approval, integration, and cleanup are separate states.
- Timeout/disconnect requires reconcile before retry.
- Observer EventBus hooks are not enforcement authority.
- `AUTO_CHAIN=false` and workers cannot self-approve or self-integrate.

## Verification commands

```bash
git rev-parse --show-toplevel
git branch --show-current
git status --short --branch
git worktree list --porcelain
git diff --check
```

## Evidence required

- Current root/branch/HEAD/dirty/worktree snapshot.
- Contract contains all lane, identity, authority, recovery, and cleanup invariants.
- No runtime files or unrelated campaign files changed.

## Exit criteria

P0 is complete only when the scoped commit exists and the INDEX marks P1 as
the sole next frontier. P0 does not claim runtime improvement.

## Block classification

- `HARD_BLOCK`: conflict with route/lifecycle authority or inability to bind the Task Card.
- `RECOVERABLE_BLOCK`: transient Git/index/tool failure with files preserved.
