---
artifact_authority: current
owner: James Chen
status: COMPLETE
campaign_id: github-issue-150-skill-descriptor-impact-map-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/150
baseline_main: 02d9ff25b1e5ac2dab12c8cb3d40a7a97416da6c
historical_baseline: 02d9ff25b1e5ac2dab12c8cb3d40a7a97416da6c
reconciled_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
current_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
ordered_cards:
  - 01-skill-descriptor-impact-map.md
current_frontier: TERMINAL_RECONCILIATION
frontier_status: COMPLETE
completed_cards:
  - 01-skill-descriptor-impact-map.md
blocked_cards: []
AUTO_CHAIN: false
terminal_marker: SKILL_DESCRIPTOR_IMPACT_MAP_PROVEN
claim_ceiling: SKILL_DESCRIPTOR_ARTIFACT_CONTRACT_AND_IMPACT_MAP_ONLY
physical_receipt:
  pull_request: 160
  candidate_head: f5fa2a74aacb8481e1a40b7f1349e258ede73871
  merge_commit: c7e60f4c6798554e51cbc322ebfaf89e2c5cc346
  changed_files: 5
  focused_tests: 52
  required_checks: SUCCESS
  tier3: SKIPPED_EXPECTED
---

Historical source-PR current-main binding: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; retained as historical evidence after the Issue #428 active rebind.

Prior readback binding `cdf2570ede5ae218f36f886b696c8da45458043a`
(2026-08-14) is retained as historical only.

# Issue 150 Skill Descriptor Impact Mapping

Add a repository-artifact contract for `.agents/skills/**` descriptors and a
conservative impact-map prefix so descriptor changes select the artifact,
catalog, schema, and CI trust checks without weakening unknown-path fallback.

PR #160 physically merged this bounded artifact contract and impact mapping.
This reconciliation proves descriptor validation and impact selection only; it
does not grant #138, runtime, catalog implementation, route, Workforce,
release, or production authority.
