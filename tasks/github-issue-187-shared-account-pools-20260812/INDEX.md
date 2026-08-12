---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-187-shared-account-pools-20260812
source_campaign_issue: https://github.com/James3014/Nexus-new/issues/187
baseline_main: bc16cbf2bf00377a4521e3eab233175112d0c963
current_main: 21add665679acaa57a795296dfef2f5b4e49af27
ordered_cards:
  - 01-account-lease-contract.md
  - 02-agy-lease-continuation.md
current_frontier: 02-agy-lease-continuation.md
completed_cards:
  - 01-account-lease-contract.md
blocked_cards: []
AUTO_CHAIN: false
---

# Shared Agy/Grok Account Pools

Issue #190 is closed after independent acceptance, protected merge PR #201, and post-merge readback on `main@21add665679acaa57a795296dfef2f5b4e49af27`.

Current selected mutation frontier: `02-agy-lease-continuation.md` / Issue #191.

Issue #192 has its #190 contract dependency satisfied, but it is not the selected mutation frontier. Do not dispatch #192 in parallel under this campaign unless the Owner explicitly changes the single-frontier policy. Issues #193-#196 remain downstream.

The local Nexus checkout is not collaboration-current; GitHub `main` is the source authority for this frontier. Local credentials/account profiles remain machine-local and are not repository inputs.

Maximum campaign claim at this frontier: `agy_request_lease_continuation_candidate_only`.
