# Campaign Index: External Intelligence V10 Current-Main Canary R3

artifact_authority: current
owner: James Chen
status: ACTIVE
campaign_id: `external-intelligence-v10-current-main-canary-20260823-r3`
current_frontier: `00-current-main-unattended-canary-r3`
completed_cards: []
AUTO_CHAIN: false
claim_ceiling: `TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE`

## Campaign Overview

Track Issue #530's fresh current-main EIA unattended canary. Historical Issue
#349 and its R2 execution identity remain immutable. This campaign exists only
to create a fresh Task Card, task identity, and unit identity so current-main
execution cannot reuse the prior fanout/closure receipts.

The actual dispatch-time `main_sha` is supplied only by Issue #530's fenced
contract after this card is merged and the EIA runtime has been rebound to that
exact post-merge main. The contract must bind the exact raw Git-blob SHA-256 of
the Task Card at that commit.

## Ordered Cards

1. [00-current-main-unattended-canary-r3.md](00-current-main-unattended-canary-r3.md) - `eia-v10-current-main-canary-20260823-r3`

## Current Frontier

`eia-v10-current-main-canary-20260823-r3`

## Ready Cards

- `eia-v10-current-main-canary-20260823-r3`

## Completed Cards

- none

## Campaign Boundaries

- Preserve all historical EIA automation/fanout/session/receipt state.
- Do not mutate the canonical runtime root from a worker Candidate.
- Do not change AGENTS/MUSE/GEMINI/CLAUDE/MEMORY/SOUL/Cursor bootstrap files.
- Do not change production source, workflow, route, policy, provider, or credentials.
- No deletions; no release or production claims; no manual `run-once` substitute.
- `AUTO_CHAIN=false`; completion never self-authorizes another Task Card.

## Downstream Gate

After this campaign is merged, the coordinator must re-read canonical `main`,
safely rebind/restart the dedicated EIA runtime to that exact source,
independently re-prove public `READY`, compute this Task Card's exact raw Git
blob SHA-256 at that post-merge main, install exactly one fresh Issue #530 fenced
contract, and add `nexus:external-intelligence` as the final arming mutation.
No manual execution substitute is allowed afterward.
