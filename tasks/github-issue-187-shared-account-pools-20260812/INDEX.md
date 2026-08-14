---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-187-shared-account-pools-20260812
source_campaign_issue: https://github.com/James3014/Nexus-new/issues/187
baseline_main: 37526fc9705cf984b0b2fd9f373460b3c98d7391
ordered_cards:
  - 01-account-lease-contract.md
  - 02-agy-lease-continuation.md
current_frontier: 02-agy-lease-continuation.md
completed_cards:
  - 01-account-lease-contract.md
blocked_cards: []
AUTO_CHAIN: false
---

# Shared Agy/Grok Account Pools — Issue #191 Frontier

This campaign currently implements only the Agy adaptation of the merged provider-neutral request-scoped account lease contract: immutable per-request Agy account binding, eligible account/provider failover, and bounded fresh-session continuation inside the existing Agy worker path.

Issue #190 / `01-account-lease-contract.md` is complete and merged through PR #201. Current frontier is `02-agy-lease-continuation.md` for Issue #191.

Issue #192 remains `SERIALIZE_AFTER:#191` and must not begin implementation until #191 has an independently accepted merged Candidate plus post-merge reconciliation. Issues #193-#196 remain transitively blocked by their direct predecessors.

Issue #191 candidate (PR #237) is open and rebased after the authorized PR #239 merge onto `nexus-new/main@37526fc9705cf984b0b2fd9f373460b3c98d7391`; current head `7e216d8769a07589f80615f3f2470abaddde0a62`, exact four files / zero deletions, 94 local tests passed, exact-head required checks and exact-base impact terminal success, independently accepted `MERGE_SLOT_ONLY`; only the Owner merge slot remains. It is not yet merged. No new #191 implementation is authorized by this reconciliation and no readiness/merge overclaim is made.

`CapabilityPlanner` remains sole route/capability selection authority. This campaign does not authorize credential mutation, provider login/logout, Codex integration, Grok implementation, approval/integration, runtime activation, production readiness, or public claims.

Maximum campaign claim at this frontier: `agy_request_scoped_lease_continuation_candidate_only`.
