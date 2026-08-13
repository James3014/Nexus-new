---
artifact_authority: current
owner: James Chen
status: active
purpose: Remove eight duplicated, repository-unwired Issue #55 experiment scripts.
authority: Owner-authorized Ready Issue #55 and this exact card
baseline: 2c820eab67669ab63297bf76fcf1751aaa9496ba
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

# Issue #55 Abandoned Experiment Cleanup

Delete only the eight paths listed in `allowed_files` and remove their exact
inventory rows. Repository evidence must rule out source, test, CLI, CI,
entry-point, package, dynamic-import, and current-document consumers. Archive
reports and `scripts/idea_check_v2.py` are explicitly retained. Undocumented
external/manual launchers cannot be disproven by repository inspection; record
that limitation without inventing runtime ownership.
