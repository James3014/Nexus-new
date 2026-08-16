---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-204-issue51-impact-map
campaign_id: github-issue-204-issue51-impact-map-20260812
source_issue: https://github.com/James3014/Nexus-new/issues/204
baseline_main: bdcc427f6249406079c85f9725b3af6cd62ab1f1
historical_baseline: bdcc427f6249406079c85f9725b3af6cd62ab1f1
reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
AUTO_CHAIN: false
block_class: NONE
completion_marker: ISSUE_51_IMPACT_MAP_PREREQUISITE_PROVEN
claim_ceiling: ISSUE_51_IMPACT_MAP_PREREQUISITE_PROVEN_ONLY
physical_receipt:
  pull_request: 205
  candidate_head: 69bf750f811164a71871e5f6635e82e25b8139bd
  merge_commit: 8620b72e5688dc41551afb8ed5454b49d21dc5e3
  changed_files: 4
  focused_tests: 4
  required_checks: NOT_REPORTED
---

# Task Card: Issue 204 Map Issue-51 Orphan Cleanup Surfaces

## Objective

Repair exact-base test-impact routing for the four production paths that make
PR #71 fail closed as `IMPACT_UNKNOWN`, without broadening cleanup or product authority.

## Authority

- Owner request: finish Issue #51 prerequisites, then complete #51.
- Issue: `#204`
- Exact baseline: `bdcc427f6249406079c85f9725b3af6cd62ab1f1`
- AUTO_CHAIN: `false`

## Terminal reconciliation

PR #205 merged candidate `69bf750f811164a71871e5f6635e82e25b8139bd` as
`8620b72e5688dc41551afb8ed5454b49d21dc5e3` into the historical baseline. The
current and reconciled `nexus-new/main` are
`46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`. The exact four-file scope and four
focused tests are bound above; live CI status is not asserted here.

## Allowed files

- `docs/testing/test_impact_map.md`
- `tests/ops/test_issue51_cleanup_impact_map.py`
- this Task Card and INDEX

## Required mapping

Exact-file rules only:
- `nexus/committee/diversity_sampler.py` -> live committee tests plus architecture safety checks;
- `nexus/env/diff_report.py` -> architecture safety checks;
- `nexus/env/snapshot.py` -> architecture safety checks;
- `nexus/policy/compatibility.py` -> policy and architecture safety checks.

All four rules are high risk, so the selector's existing high-risk escalation
continues to add the canonical policy-gate target.

## Acceptance

- every exact path has `unmatched_paths=[]` and `fallback_used=false`;
- combined selection for all four exact paths remains explicit and high risk;
- unrelated unknown `nexus/*` path still uses fail-closed fallback;
- no broad `nexus/committee`, `nexus/env`, or `nexus/policy` prefix is introduced;
- exact-head CI and trusted verifier pass;
- independent exact-head acceptance finds no false-green broadening.

## Forbidden

No PR #71 deletion mutation, selector algorithm change, runtime/API change,
ruleset/bypass change, merge/approval authority, Workforce/lifecycle/route change,
or release/production claim.

Terminal claim: `ISSUE_51_IMPACT_MAP_PREREQUISITE_PROVEN_ONLY`, limited to the
four exact high-risk mappings and the selector's existing high-risk projection.
