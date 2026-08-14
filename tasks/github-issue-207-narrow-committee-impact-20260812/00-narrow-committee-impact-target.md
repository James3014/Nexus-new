---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-207-narrow-committee-impact-target
source_issue: https://github.com/James3014/Nexus-new/issues/207
historical_baseline: 8620b72e5688dc41551afb8ed5454b49d21dc5e3
reconciled_main: cdf2570ede5ae218f36f886b696c8da45458043a
current_main: cdf2570ede5ae218f36f886b696c8da45458043a
frontier_status: TERMINAL_RECONCILIATION
terminal_marker: ISSUE_51_COMMITTEE_IMPACT_TARGET_REPAIR_PROVEN
claim_ceiling: ISSUE_51_COMMITTEE_IMPACT_TARGET_REPAIR_PROVEN_ONLY
AUTO_CHAIN: false
---

# Task Card: Issue 207 Narrow Committee Impact Target

## Objective

Replace only the exact Issue #51 `nexus/committee/diversity_sampler.py` impact target that currently selects a collection-broken legacy directory with one collection-clean live committee witness while retaining architecture coverage and high-risk escalation.

## Authority

- Issue: `#207`
- Baseline: `8620b72e5688dc41551afb8ed5454b49d21dc5e3`
- Owner goal: complete Issue #51 prerequisites, then finish PR #71.
- AUTO_CHAIN: `false`

## Allowed files

- `docs/testing/test_impact_map.md`
- `tests/ops/test_issue51_cleanup_impact_map.py`
- this Task Card and INDEX

## Exact change

`nexus/committee/diversity_sampler.py` must map to:
- `tests/unit/committee/test_data_flow_v267.py`
- `tests/architecture/test_boundaries_v4.py`

Risk remains `high` with reason `issue51_proven_orphan_cleanup_contract`.

## Acceptance

- exact selector-focused tests pass;
- unrelated unknown committee/env paths remain fail-closed fallback;
- exact-head protected CI and trusted verifier pass;
- no broad package-prefix rule or selector-algorithm change;
- PR #71 subsequently reaches exact-base test execution/classification without the proven four legacy collection errors.

## Forbidden

No PR #71 deletion mutation, runtime/API change, ruleset/bypass change, merge/approval authority, Workforce/lifecycle/route, release, or production change.

## Physical evidence and terminal boundary

- Historical baseline: `8620b72e5688dc41551afb8ed5454b49d21dc5e3`.
- Mapping commit: `abf781ea62c1c7384031bfb47d3185d2e24ca314`.
- Exact testcase-identity commit: `cdf72a61165a006049074c137c6a0de13e4a1724`.
- Reconciled current main: `cdf2570ede5ae218f36f886b696c8da45458043a`.
- Focused current-main evidence: `tests/ops/test_issue51_cleanup_impact_map.py` — 4 passed.

`ISSUE_51_COMMITTEE_IMPACT_TARGET_REPAIR_PROVEN` is limited to the exact mapped
test targets, high-risk escalation, and fail-closed fallback behavior. Historical live
check-rollup details were not recovered and are not inferred. It grants no PR #71
deletion, selector algorithm, ruleset, merge/approval, Workforce/lifecycle/route,
runtime, release, or production authority. `AUTO_CHAIN=false`.
