---
artifact_authority: current
owner: James Chen
status: COMPLETE
purpose: Remove eight duplicated, repository-unwired Issue #55 experiment scripts.
authority: Owner-authorized Ready Issue #55 and this exact card
baseline: 2c820eab67669ab63297bf76fcf1751aaa9496ba
historical_baseline: 2c820eab67669ab63297bf76fcf1751aaa9496ba
reconciled_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
current_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
historical_reconciled_main: cdf2570ede5ae218f36f886b696c8da45458043a
frontier_status: TERMINAL_RECONCILIATION
terminal_marker: ISSUE_55_ABANDONED_EXPERIMENTS_REMOVED_AND_SOURCE_INVENTORY_VERIFIED
claim_ceiling: ISSUE_55_ABANDONED_EXPERIMENTS_REMOVED_AND_SOURCE_INVENTORY_VERIFIED_PROVEN_ONLY
implementation_commit: 092617a1d937fd31f33531e7c0539d6360a599a1
rebind_lineage_commit: 62f34b5acbc4064268426cc2455c5c6561611fc6
AUTO_CHAIN: false
allowed_files:
  - scripts/brain_b_indexer.py
  - scripts/core/brain_b_indexer.py
  - scripts/brain_b_reality_check.py
  - scripts/core/brain_b_reality_check.py
  - scripts/reality_check_v2.py
  - scripts/core/reality_check_v2.py
  - scripts/trigger_test.py
  - scripts/core/trigger_test.py
  - muse_nexus.egg-info/SOURCES.txt
  - tasks/github-issue-55-abandoned-experiments-20260813/INDEX.md
  - tasks/github-issue-55-abandoned-experiments-20260813/00-abandoned-experiments.md
  - docs/testing/test_impact_map.md
  - tests/ops/test_issue55_cleanup_impact_map.py
forbidden_scope:
  - docs/archive and full_workspace_xray historical evidence
  - scripts/idea_check_v2.py
  - Git history rewrite or credential rotation
  - replacement workflow, shim, redirect, or direct main mutation
verification:
  - repeat exact path/module/caller/AST/dynamic-import/entrypoint/CI/current-doc scans
  - prove package build and registered CLIs exclude and do not invoke deleted scripts
  - run focused packaging, CLI, inventory, and secret-pattern checks
  - compare exact baseline and post-deletion regression outcomes
  - run git diff --check and exact deletion-only audit
evidence:
  - no current repository consumer or configured launcher may remain
  - root/core pairs are byte-identical before deletion
  - embedded credentials are not repeated; historical removal is not claimed
exit_criteria: scoped commit pushed on issue branch with PR opened; no self-merge
block_class: RECOVERABLE_BLOCK
---

Historical source-PR current-main binding: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; retained as historical evidence after the Issue #428 active rebind.

# Issue #55 Abandoned Experiment Cleanup

Delete only the eight paths listed in `allowed_files` and remove their exact
inventory rows. Repository evidence must rule out source, test, CLI, CI,
entry-point, package, dynamic-import, and current-document consumers. Archive
reports and `scripts/idea_check_v2.py` are explicitly retained. Undocumented
external/manual launchers cannot be disproven by repository inspection; record
that limitation without inventing runtime ownership.

## Physical evidence and terminal boundary

- Historical baseline: `2c820eab67669ab63297bf76fcf1751aaa9496ba`.
- PR #221 base: `587aa4b1d6026dc85efe35930f2067fbd1ead3cc`.
- PR #221 head: `62f34b5acbc4064268426cc2455c5c6561611fc6`.
- PR #221 merge: `092617a1d937fd31f33531e7c0539d6360a599a1` (parents exactly
  `587aa4b1...` and `62f34b5a...`).
- Exact scope: thirteen files (eight script deletions, eight
  `muse_nexus.egg-info/SOURCES.txt` rows, `docs/testing/test_impact_map.md`,
  `tests/ops/test_issue55_cleanup_impact_map.py`, and this campaign pair).
- Exact-head workflows: Pytest, Pyright, Bandit, Ruff, and Wiki governance
  completed successfully (five runs).
- Owner receipt: `COMPLETION_RECONCILIATION` recorded on Issue #55.
- Reconciled current main: `71ae533ec9f795477131645f96cea1c93b4f4d40`
  (PR #333 merge; prior reconciled main
  `cdf2570ede5ae218f36f886b696c8da45458043a` retained as historical);
  readback confirms all eight deleted paths absent, their eight inventory rows
  absent, the eight exact impact-map rows present with
  `issue55_abandoned_experiment_cleanup_contract`, the focused impact-map
  tests pass (5 passed together with the source-inventory integrity test), and
  `scripts/idea_check_v2.py` retained.

`ISSUE_55_ABANDONED_EXPERIMENTS_REMOVED_AND_SOURCE_INVENTORY_VERIFIED` proves
only the exact GitHub collaboration deletion and source-inventory
reconciliation. It grants no runtime, route, Workforce, lifecycle, approval,
integration, merge, release, or production authority; no credential rotation,
history rewrite, or unknown external-launcher claim. `AUTO_CHAIN=false`.
