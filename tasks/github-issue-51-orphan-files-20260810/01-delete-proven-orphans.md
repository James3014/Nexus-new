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

# Delete Thirteen Proven Orphan Files

## Objective

Delete exactly the thirteen currently proven Issue #51 orphan paths without replacement or reachable behavior change. Remove the stale Wiki inventory row for the duplicate root transaction module. Preserve `legacy/logmemory.py`.

## Baseline

- GitHub main: `61ea89a85ad0e8cb453ec642293a2da9df072a4c`
- prerequisites: #75, #104, #105, #106, #204, and #207 physically completed
- existing PR: #71, rebound to this exact baseline before verification

## Authorized deletions

- `nexus/policy/compatibility.py`
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

## Required retained path

- `legacy/logmemory.py` must remain byte-identical to baseline. It contains an executable CLI entrypoint and is not admitted for deletion.

## Allowed documentation correction

- `nexus_wiki_vault/90_Sources/Source - Coverage Heatmap.md`: delete only the stale row for `nexus/core/nexus_transaction.py`.

## Required controls

- exact caller/import/registration/packaging search must not reveal a live user of any deleted path;
- zero-byte placeholders must remain zero-byte at the bound baseline;
- `nexus/core/nexus_transaction.py` must remain byte-identical to the retained `nexus/core/engine/nexus_transaction.py` before deletion;
- no replacement, refactor, dependency, route, lifecycle, Workforce, authority, generated artifact, or historical report change;
- required protected checks must bind the exact candidate head and trusted GitHub Actions integration;
- integration must use the #106 exact-head CAS/post-apply contract and stop on base/head/tree/check/path drift.

## Verification

- per-path caller and executable-content audit;
- retained canonical transaction/coordinator focused tests;
- exact-base impact gate, Ruff, Pyright, Bandit, Wiki governance, and trusted verifier on the exact candidate;
- full exact-base/post-change regression comparison preserving all pre-existing debt;
- exact deletion manifest, `git diff --check`, and changed-path scope audit;
- post-merge verify resulting main tree, exact merge parents, all thirteen paths absent, retained legacy path present, and stale Wiki row absent.

## Exit

Every physical deletion is individually supported, no executable test behavior is deleted, no current caller remains, no new regression is introduced, and an independent exact-head acceptance accepts the bounded diff.

Maximum candidate claim: `ISSUE_51_ORPHAN_CLEANUP_CANDIDATE`.
