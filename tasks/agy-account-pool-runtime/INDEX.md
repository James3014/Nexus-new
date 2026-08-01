---
artifact_authority: current
owner: James3014/Nexus
status: active, governed and sequential
campaign_id: agy-account-pool-runtime
source_spec: Corrected governed AGY account-pool runtime integration
ordered_cards:
  - 00-agy-account-pool-runtime-integration.md
  - 01-agy-account-pool-real-manager-runtime-closure.md
  - 02-agy-gateway-executable-authority-convergence.md
  - 03-agy-card01-live-dispatch-acceptance.md
dependencies: []
current_frontier: 03-agy-card01-live-dispatch-acceptance.md
completed_cards:
  - 00-agy-account-pool-runtime-integration.md
card_01:
  path: 01-agy-account-pool-real-manager-runtime-closure.md
  status: IMPLEMENTED_PENDING_CARD_03_LIVE_ACCEPTANCE
card_02:
  path: 02-agy-gateway-executable-authority-convergence.md
  status: IMPLEMENTED_PENDING_CARD_03_LIVE_ACCEPTANCE
card_03:
  path: 03-agy-card01-live-dispatch-acceptance.md
  status: ACTIVE_LIVE_ACCEPTANCE
blocked_cards: []
superseded_cards: []
retained_targets:
  - path: /private/tmp/nexus-agy-governance-targets/agy-account-pool-runtime-integration-a1
    status: RETAINED_SUPERSEDED_BY_A2
    note: Target A1 retained as read-only reference; superseded by clean Controller target A2 integration.
AUTO_CHAIN: false
---

# AGY Account Pool Runtime Campaign Index

This campaign governs the deterministic, test-isolated AGY account pool integration into `AgyWorkerAdapter`.

## Target Retention & Supersession
- Target A1 (`/private/tmp/nexus-agy-governance-targets/agy-account-pool-runtime-integration-a1`): Retained as read-only reference, superseded by A2.
- Target A2 (`/private/tmp/nexus-agy-governance-targets/agy-account-pool-runtime-integration-a2`): Current active Controller target for candidate promotion.
- The 00 integration is historical evidence only until 01 proves real manager execution; its memory-only account list is not production runtime proof.
