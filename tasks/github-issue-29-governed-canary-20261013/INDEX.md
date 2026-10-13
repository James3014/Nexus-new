# Campaign Index: Issue #29 governed Local -> Online consumption canary (2026-10-13)

artifact_authority: current
owner: James Chen
status: ACTIVE
campaign_id: `github-issue-29-governed-canary-20261013`
current_frontier: `00-governed-local-online-canary`
completed_cards: []
AUTO_CHAIN: false
claim_ceiling: `ONE_GOVERNED_CANARY_RECEIPT_PENDING_INDEPENDENT_REVIEW`

## Campaign Overview

Refreshes the Issue #29 Task Card per the Owner decisions of 2026-10-13:
Online `agy_flash_38` / `gemini-3.8-flash-medium` with no fallback, Agy in
`--mode plan --sandbox` with the VAP inline, host preflight before any physical
run, and a governed-path harness that replaces the PR #1408 script. The
2026-10-05 campaign (`tasks/github-issue-29-local-online-canary-20261005/`)
stays unchanged as history.

## Ordered Cards

1. [00-governed-local-online-canary.md](00-governed-local-online-canary.md) - `github-issue-29-governed-canary-20261013-r1`

## Current Frontier

`github-issue-29-governed-canary-20261013-r1`

## Ready Cards

- `github-issue-29-governed-canary-20261013-r1` (physical run is Owner-gated)

## Completed Cards

- none

## Campaign Boundaries

- No service changes, no extra Ollama/Splash instances, no Agy `settings.json` change.
- No fallback model; not admitted -> `BLOCKED`, return to the Owner.
- No deletions; no merge, release, model promotion, or public claim from this campaign.
- `AUTO_CHAIN=false`; completion never self-authorizes another card.
