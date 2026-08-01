# Task Card P0: Single MCP Three-Lane Authority

## Identity

- task_id: `single-mcp-three-lane-p0-authority`
- campaign_id: `single-mcp-three-lane-fast-dispatch`
- artifact_authority: current
- status: COMPLETED
- owner: James Chen
- objective: Establish the current Git-tracked authority and bounded implementation frontier for the single MCP three-lane fast-dispatch campaign.
- read_only: false
- audit_only: false
- commit_required: true
- candidate_required: false
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Inputs and Dependencies

- `/Users/jameschen/.codex/attachments/c3d4b685-035e-4609-89b7-f0781c8b0307/pasted-text-1.txt`
- `tasks/lifecycle-two-lane-canonical-closure/INDEX.md`
- `docs/arch/MODEL_WORKFORCE_POLICY.md`
- `nexus/config/model_workforce.yaml`
- Current canonical Git state and lifecycle inventory

## Allowed Files

- `tasks/single-mcp-three-lane-fast-dispatch/INDEX.md`
- `tasks/single-mcp-three-lane-fast-dispatch/00-p0-authority.md`

## Required Behavior

1. Record the canonical root, lifecycle state root, Target root, retired root, and current frontier.
2. Preserve the existing two-lane lifecycle as the authority for isolated Target cleanup and owner approval.
3. Define the downstream three-lane contract without implementing runtime behavior in this bootstrap card.
4. Keep external DevSpace source read-only until the runtime cutover card has its own allowed files and gates.

## Verification Commands

```bash
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git status --short --branch
git worktree list --porcelain
.venv/bin/python -m scripts.engine.nexus_cli self-hosted list-actionable
```

## Exit Criteria

- The index and card are tracked in one scoped commit.
- The index names this card as the only current frontier.
- The card contains explicit allowed and forbidden scope, verification, and completion gates.
- Canonical lifecycle actionable count remains zero and no Target is created.

## Completion Evidence

- Scoped commit: `d5a4547d28c44696effaa79e176ef75dbac9475e`
- Direct receipt: `cb5c9c358c3062777e69c1a92e54719a5b60ba02f635cfaf5e6a5a3e450e11f5`
- Verification: `git diff --check` passed; `state_created=false`; `target_created=false`.

## Block Classification

- `RECOVERABLE_BLOCK`: lifecycle CLI or verifier unavailable while the card remains unchanged.
- `HARD_BLOCK`: canonical branch/root drift, active actionable lifecycle work, or a request to mutate the retired/external workspace.
