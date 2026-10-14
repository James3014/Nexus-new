# Campaign Index: External Intelligence Open-SWE Canary (2026-10-14, ChatGPT Team / GPT-5.6 transport)

artifact_authority: current
owner: James Chen
status: ACTIVE
campaign_id: `external-intelligence-open-swe-canary-20261014`
current_frontier: `00-open-swe-unattended-canary`
completed_cards: []
AUTO_CHAIN: false
claim_ceiling: `TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE`

## Campaign Overview

Track one unattended EIA canary on the open-swe semantic and worker backends
after the owner moved the ChatGPT Web transport to the owner's ChatGPT Team
workspace with GPT-5.6 Sol at the highest reasoning effort (2026-10-14).
Historical Issues #349, #530 and #1828 and their execution identities remain
immutable.

The actual dispatch-time `main_sha` is supplied only by the canary Issue's
fenced contract after this card is merged. The contract must bind the exact raw
Git-blob SHA-256 of the Task Card at that commit.

## Ordered Cards

1. [00-open-swe-unattended-canary.md](00-open-swe-unattended-canary.md) - `eia-open-swe-canary-20261014`

## Current Frontier

`eia-open-swe-canary-20261014`

## Ready Cards

- `eia-open-swe-canary-20261014`

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
compute this Task Card's exact raw Git blob SHA-256 at that post-merge main,
install exactly one fenced contract on the canary Issue, and add
`nexus:external-intelligence` as the final arming mutation. No manual execution
substitute is allowed afterward.

## Exit criteria

Exactly one completion publication is emitted for the canary Issue with
`current_gate=PENDING_INDEPENDENT_ACCEPTANCE`; this card's raw blob SHA-256
exactly equals the Issue `task_card_hash`; exactly one open-swe semantic and
worker execution occurs under the new task/unit identity; the Candidate changes
only `tests/ops/test_external_intelligence_open_swe_canary_20261014.py`; unit
and whole-task verifiers pass; the dedicated EIA checkout remains clean; and the
daemon remains public `READY` after the run.
