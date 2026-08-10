---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-51-delete-proven-orphans
campaign_id: github-issue-51-orphan-files-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/51
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Delete Fourteen Proven Orphan Files

## Objective

Delete exactly the fourteen Issue #51 orphan paths without replacement or any
reachable behavior change. Remove the stale Wiki inventory row for the root
transaction duplicate only if it remains exact and isolated.

## Baseline

- GitHub main: `14dd1f29183b09646215462b97b0dd0feb8c0743`
- fresh re-anchor comment: https://github.com/James3014/Nexus-new/issues/51#issuecomment-5234633899

## Authorized deletions

- `nexus/policy/compatibility.py`
- `legacy/logmemory.py`
- `nexus/committee/diversity_sampler.py`
- `nexus/env/diff_report.py`
- `nexus/env/snapshot.py`
- `nexus/research/reporting/report_writer.py`
- `nexus/retry_policy/contracts.py`
- `tests/unit/calibration/test_metrics.py`
- `tests/unit/committee/test_abstain.py`
- `tests/unit/committee/test_adapter.py`
- `tests/unit/committee/test_comparator.py`
- `tests/unit/committee/test_critics.py`
- `tests/unit/env/test_denoiser_split.py`
- `nexus/core/nexus_transaction.py`

## Optional allowed edit

- `nexus_wiki_vault/90_Sources/Source - Coverage Heatmap.md`: delete only the
  stale row for `nexus/core/nexus_transaction.py`.

Maximum source paths changed: 15. Task Card files are authorization artifacts.

## Required controls

- repeat exact import/symbol/path search before deletion;
- if any live caller, dynamic registration, package export, CI/CLI/config
  consumer, or executable content is found, do not delete that path;
- preserve the retained `nexus.core.engine.nexus_transaction` implementation;
- no replacement, refactor, formatting sweep, generated artifact, dependency,
  authority, lifecycle, route, workforce, or historical report change.

## Verification

- per-path caller and executable-content audit before and after deletion;
- retained canonical transaction/coordinator focused tests;
- Ruff on remaining touched Python surface where applicable;
- exact deletion audit and zero unexpected additions;
- full exact-base/post-change regression comparison, including collected test
  count and failure/error node IDs;
- `git diff --check` and complete staged/unstaged stats.

## Exit

Every physical deletion is individually proven, no executable test is removed,
no current caller remains, no regression is introduced, and an independent
exact-commit review accepts the bounded diff.

## Block class

`RECOVERABLE_BLOCK` for a path whose orphan proof fails; omit that path and
continue the independently proven subset. `HARD_BLOCK` for any request to adapt
a caller or alter reachable behavior under this cleanup card.
