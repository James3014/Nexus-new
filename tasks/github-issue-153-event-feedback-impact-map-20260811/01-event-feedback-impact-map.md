---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-153-event-feedback-impact-map
campaign_id: github-issue-153-event-feedback-impact-map-20260811
source_issue: https://github.com/James3014/Nexus-new/issues/153
baseline_main: 9dddd018ad2761face3d2f3ce29dff8d8feae72d
implementation_commit: 4ffbd1fa7e4b88c932615daf3dfa3dec9e8ecd7b
rebind_lineage_commit: 88a6c616fdf145738e582aa625c94abbf90daf66
AUTO_CHAIN: false
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: true
---

# Event and feedback impact-map coverage

## Objective

Add exact impact-map rows for the existing `nexus/events` and `nexus/feedback`
authority prefixes, preserving unmatched fallback and existing selector
semantics.

## Allowed files

- `docs/testing/test_impact_map.md`
- `tests/ops/test_select_tests.py`
- this card and its `INDEX.md`

## Forbidden scope

- `scripts/ops/select_tests.py`
- `scripts/ops/pr_impact_gate.py`
- PR #151 files
- workflows, runtime, routing, lifecycle, Workforce, claim, approval, or
  authority changes
- broad `nexus` or arbitrary `nexus/events*` mappings
- weakening fallback, Tier2, or `IMPACT_UNKNOWN`

## Acceptance

- Event files select `tests/events`, `tests/core/test_event_bus.py`, and
  `tests/architecture/test_boundaries_v4.py` with high risk and no fallback.
- Feedback files select `tests/events`, policy/committee data-flow tests, and
  architecture boundary v3/v4 tests with high risk and no fallback.
- Mixed event+feedback inputs union and deduplicate deterministically.
- Unknown event/feedback prefixes remain unmatched and use fallback.
- Existing most-specific-prefix behavior remains unchanged.

## Verification

- focused selector tests and real JSON probes
- Ruff check and preview-format on changed Python
- compileall on changed Python
- `git diff --check`
- exact three-file implementation scope audit, plus this card/INDEX

## Claim ceiling

`EVENT_AND_FEEDBACK_IMPACT_MAPPING_CANDIDATE_ONLY`

Final exact PR head identity is supplied by the external PR/protected-check/
merge receipt, not recursively stored in this card.
