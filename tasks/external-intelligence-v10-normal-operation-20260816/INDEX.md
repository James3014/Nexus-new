# Campaign Index: External Intelligence V10 Normal Operation

artifact_authority: current
owner: James Chen
status: ACTIVE
campaign_id: `external-intelligence-v10-normal-operation-20260816`
current_frontier: `00-v10-normal-operation`
completed_cards: []
AUTO_CHAIN: false
main_sha: `8f9b555739f828ae1c65e3d0c6f11e7755c96068`
claim_ceiling: `TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE`

## Campaign Overview

Track the single EIA V10 normal-operation canary Task Card for Issue #349. The
campaign proves the External Intelligence Automation daemon can discover,
validate, execute, verify, and close one approved read-only Task Card
unattended from canonical main after PR331 execution-authority hardening. It
adds no implementation, runtime, route, provider, or merge authority.

## Ordered Cards

1. [00-v10-normal-operation.md](00-v10-normal-operation.md) - `eia-v10-normal-operation-20260816`

## Current Frontier

`eia-v10-normal-operation-20260816`

## Ready Cards

- none

## Completed Cards

- none

## Blocked Cards

- none

## Campaign Boundaries

- Do not mutate the canonical runtime root.
- Do not change AGENTS/MUSE/GEMINI/CLAUDE/MEMORY/SOUL/Cursor bootstrap files.
- Do not change production source, workflow, route, policy, provider, or credentials.
- Do not create a second selector/router/planner authority.
- No deletions; no release or production claims; no manual run-once substitute.
- `AUTO_CHAIN=false`; completion never self-authorizes the next card.

## Downstream Gate

Owner/coordinator arming of Issue #349 (contract plus trigger label) is
required before the daemon may consume this card. Until armed, V10 is not
active and has not been consumed.
