---
artifact_authority: current
owner: James Chen
status: active
purpose: Update the night queue's requested worker role to bounded_candidate_generation.
issue: 111
---

## Objective

Update the night queue's requested worker role from `bounded_implementation` to `bounded_candidate_generation`, matching the formal OpenCode L1 roster role used by MiMo and Ling.

## Inputs and Current Analysis

- Baseline: `main=4cf1a3519d7937f71a664bd347efd7c4eb0b4d1e`
- Analysis:
  - SQLite queue (`queue_manager.py`) is missing its consumer `scripts/codex_loop_brain.py` (physically deleted).
  - Nightshift pending manifest (`pending.json`) has no consumer in the entire codebase.
  - Workforce Admission (`model_workforce_policy.py`) has no seam for night queue or applicable OpenCode L1 path role routing.
  - Therefore, a unique producer ➔ consumer contract cannot be established from the current source.

## Allowed files

- `tasks/github-issue-111-night-queue-20260812/INDEX.md`
- `tasks/github-issue-111-night-queue-20260812/01-night-queue-update.md`

File-count ceiling: two files.

## Required behavior

- Declare CONTRACT_DELTA due to broken queue consumer and lack of Workforce Admission seam in current source.
- Do not modify provider/model identity, CapabilityPlanner route authority, default route, or review/approval/integration/push authority.
- Do not create secondary queue or Workforce authority.

## Forbidden scope

No modifications to the core workforce policies, models, or dispatch logic under broken contracts. No PR self-merges.

## Verification

1. Audit codebase structure for consumer and seam existence.
2. Confirm baseline PR #110 merge state.

## Exit criteria & Block classification

- `CONTRACT_DELTA`: Resolved as stopped due to lack of valid consumer and workforce seam. Escalate to Owner.
- `HARD_BLOCK`: Any attempt to manually forge or invent a secondary queue or Workforce authority.
