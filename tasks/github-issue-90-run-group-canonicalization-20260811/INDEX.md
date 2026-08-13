---
artifact_authority: current
owner: James Chen
status: COMPLETE
campaign_id: github-issue-90-run-group-canonicalization-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/90
baseline_main: 0b97df90bbebbd90d0811d46ba73c47e46fe1878
historical_baseline: 0b97df90bbebbd90d0811d46ba73c47e46fe1878
reconciled_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
current_main: eb668fb76f0c30d8f025db42cdb8e320d556c037
ordered_cards:
  - 01-run-group-canonicalization.md
current_frontier: TERMINAL_RECONCILIATION
frontier_status: COMPLETE
completed_cards:
  - 01-run-group-canonicalization.md
blocked_cards: []
AUTO_CHAIN: false
terminal_marker: WORLD_C_RUN_GROUP_CANONICALIZATION_PROVEN
claim_ceiling: WORLD_C_S1_RUN_GROUP_CANONICALIZATION_PROVEN_ONLY
physical_receipt:
  pull_request: 155
  candidate_head: 000274fe44b0b5ae1250fa7fc0fec0cd673b4e47
  merge_commit: 8e05e0827fe913e3e408f87dc274e005bdc0bf92
  changed_files: 4
  focused_tests: 17
  required_checks: SUCCESS
admission_policy_hash: 1ed56a4cd4d7ba43ce7dc7c0fbeab470f078b39d6561e580a03fd92826890b77
admission_binding_hash: 86615e3f55592c67a72a8e0fa23a3300c27176a609af1dd8bb4692bf6606eb90
admission_aggregate_binding_hash: 7b7f175de7209db198096c29d625d18c535b993f8e8643e337fc4864daafe9e8
---

# Issue 90 Run-Group Canonicalization

PR #155 physically merged the fail-closed LocalHeal repair-receipt `run_group`
canonicalization. This reconciliation proves World C S1 run-group identity
only; #91 and #95 remain separate. It grants no broader World C, runtime,
route, planner, provider, Workforce, approval, integration, merge, release, or
production authority.
