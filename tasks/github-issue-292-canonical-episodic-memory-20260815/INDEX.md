---
campaign_id: github-issue-292-canonical-episodic-memory-20260815
issue: 292
repository: James3014/Nexus-new
status: ACTIVE
baseline_main: 19d815954ff72e99ed50734410cd2342a0b62bc7
current_main: d181a653d4a155266bf9e97fdfe35b69d3f08991
current_frontier: NONE
frontier_status: G3_SOURCE_LOCALIZATION_PENDING
completed_cards:
  - github-issue-292-canonical-episodic-memory-g2-20260815
completion_marker: CANONICAL_EPISODIC_MEMORY_G2_APPLICABILITY_PROVEN
claim_ceiling: canonical_episodic_memory_g2_source_and_tests_only
AUTO_CHAIN: false
authorized_deletions: []
---

# Issue #292 — canonical episodic memory

Issue #292 is decomposed into independently bounded G1–G4 slices. G1 is
physically merged through PR #295 (`ccd23defe9aa5905d26f34a865746c1eff7d039f`)
and G2 is physically merged through PR #303
(`d181a653d4a155266bf9e97fdfe35b69d3f08991`). Both are ancestors of current
main. No G3 Task Card has been frozen; the next gate is read-only G3 source and
overlap localization.

- Current frontier: none; `G3_SOURCE_LOCALIZATION_PENDING`.
- G1 physical receipt: PR #295 merge `ccd23defe9aa5905d26f34a865746c1eff7d039f`; historical campaign baseline `cdf2570ede5ae218f36f886b696c8da45458043a`.
- G2 physical receipt: PR #303 head `c06ba7dc160af5b0ef0a0165d39ee89a47f57af3`; merge/current main `d181a653d4a155266bf9e97fdfe35b69d3f08991`; exact four-file PR scope, zero deletions; focused `52 passed`; required exact-head checks successful with Tier 3 skipped by policy.
- G2 implementation-only diff SHA-256: `8a16e6595da0cd23a674305bc5a2b6502418dab4b1f27373e0128bd3769bc7d6`.
- Completion marker: `CANONICAL_EPISODIC_MEMORY_G2_APPLICABILITY_PROVEN`.
- G3–G4 implementation is not authorized by this reconciliation.
- `AUTO_CHAIN=false`.
- Claim ceiling: `canonical_episodic_memory_g2_source_and_tests_only`.
