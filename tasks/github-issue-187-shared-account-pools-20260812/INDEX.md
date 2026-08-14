---
artifact_authority: current
owner: James Chen
status: active
campaign_id: github-issue-187-shared-account-pools-20260812
source_campaign_issue: https://github.com/James3014/Nexus-new/issues/187
baseline_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
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

Issue #191 candidate (PR #237 head `7c66d005a0ed736351a125a13b10278633c00165`) is open and unaccepted; it stays impact-blocked until PR #239 merges, then requires rebind/rerun before independent acceptance. No new #191 implementation is authorized by this reconciliation.

`CapabilityPlanner` remains sole route/capability selection authority. This campaign does not authorize credential mutation, provider login/logout, Codex integration, Grok implementation, approval/integration, runtime activation, production readiness, or public claims.

Maximum campaign claim at this frontier: `agy_request_scoped_lease_continuation_candidate_only`.
