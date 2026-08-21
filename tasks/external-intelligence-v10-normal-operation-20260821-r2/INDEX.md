# Campaign Index: External Intelligence V10 Normal Operation R2

artifact_authority: current
owner: James Chen
status: ACTIVE
campaign_id: `external-intelligence-v10-normal-operation-20260821-r2`
current_frontier: `00-v10-normal-operation-r2`
completed_cards: []
AUTO_CHAIN: false
claim_ceiling: `TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE`

## Campaign Overview

Track the replacement execution identity for Issue #349's single EIA V10
normal-operation canary. The historical execution identity
`eia-v10-normal-operation-20260816` remains immutable because its initial
semantic dispatch reached a durable terminal replay fence. This campaign does
not erase, retry, or reinterpret that attempt.

The new identity preserves the same harmless canary objective while obtaining a
new `task_id` and unit identity. Dispatch-time source authority is bound only by
the Issue #349 fenced contract's exact `main_sha`, the exact raw Git-blob
SHA-256 of the Task Card at that commit, and the card authority parsed from that
blob. This index intentionally carries no card-local dispatch-time main SHA.

## Ordered Cards

1. [00-v10-normal-operation-r2.md](00-v10-normal-operation-r2.md) - `eia-v10-normal-operation-20260821-r2`

## Current Frontier

`eia-v10-normal-operation-20260821-r2`

## Ready Cards

- `eia-v10-normal-operation-20260821-r2`

## Completed Cards

- none

## Blocked Cards

- none

## Campaign Boundaries

- Preserve all historical V10 automation/fanout/session/receipt state.
- Do not mutate the canonical runtime root from a worker Candidate.
- Do not change AGENTS/MUSE/GEMINI/CLAUDE/MEMORY/SOUL/Cursor bootstrap files.
- Do not change production source, workflow, route, policy, provider, or credentials.
- Do not create a second selector/router/planner authority.
- No deletions; no release or production claims; no manual run-once substitute.
- `AUTO_CHAIN=false`; completion never self-authorizes another Task Card.

## Downstream Gate

After this campaign is merged, the coordinator must re-read the new canonical
`main`, rebind/restart the already-supported EIA runtime to that exact source,
independently re-prove `READY`, compute the Task Card's exact raw Git-blob
SHA-256 at that post-merge main, then install exactly one fresh Issue #349
fenced contract and add `nexus:external-intelligence` as the final arming
mutation. No manual execution substitute is allowed afterward.
