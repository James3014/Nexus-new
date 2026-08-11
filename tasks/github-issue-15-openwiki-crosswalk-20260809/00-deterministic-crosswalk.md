---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-15-deterministic-crosswalk
campaign_id: github-issue-15-openwiki-crosswalk-20260809
source_issue: https://github.com/James3014/Nexus-new/issues/15
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

# Task Card: Deterministic OpenWiki to Governed Wiki Crosswalk

## Objective

Compile physically declared OpenWiki implementation paths into deterministic
governed-Wiki authority mappings without creating or inferring authority.

## Dependencies

- Issue #15 is Ready through its post-#10 reconciliation comment.
- Issue #10 closed and PR #20 merged.
- Exact base: `d934a7c49d40ea7ec908f754845965fa11103ae6`.

## Allowed files

- `scripts/ops/openwiki_authority_crosswalk.py`
- `tests/ops/test_openwiki_authority_crosswalk.py`
- `tasks/github-issue-15-openwiki-crosswalk-20260809/INDEX.md`
- `tasks/github-issue-15-openwiki-crosswalk-20260809/00-deterministic-crosswalk.md`

Maximum changed files: 4.

## Forbidden scope

- OpenWiki or governed-Wiki prose/content mutation
- `WIKI_AUTHORITY_MANIFEST.yaml` changes
- Generated vault artifact edits
- Fuzzy, embedding, filename, prose, or LLM authority selection
- Route, Planner, workforce, lifecycle, approval, integration, or runtime code

## Verification

- `/Users/jameschen/Workspace/nexus/.venv/bin/python -m pytest -q tests/ops/test_openwiki_authority_crosswalk.py tests/ops/test_openwiki_source_contract.py`
- `/Users/jameschen/Workspace/nexus/.venv/bin/ruff check scripts/ops/openwiki_authority_crosswalk.py tests/ops/test_openwiki_authority_crosswalk.py`
- Two independent compilations must be byte-identical
- `git diff --check`

## Required evidence

- Exact base and card SHA-256
- Mapped core/engine, services, and scripts/ops examples
- Real unmapped path and fail-closed ambiguity/precedence fixtures
- Complete scoped diff and independent review

## Exit criteria

- Output is deterministic and explicitly `derived_non_authoritative`.
- Every destination comes only from current manifest rules.
- No fuzzy or inferred destination is possible.
- Closure records whether existing drift/alignment tooling needs a bounded
  follow-up Issue.

## Block classification

- `RECOVERABLE_BLOCK`: focused implementation/test failure.
- `HARD_BLOCK`: deterministic artifact home or authority contract conflicts.

## Completion evidence

- Exact base: `d934a7c49d40ea7ec908f754845965fa11103ae6`.
- Deterministic output: 22 records, 10 `EXACT_PREFIX_MATCH`, 12 `UNMAPPED`.
- Two independent compilations were byte-identical.
- Focused suite: 18 passed; Ruff and `git diff --check` passed.
- Independent Luna review: `ACCEPT` after strict manifest schema,
  duplicate-key, and authority-field validation.
- Post-pilot decision: `BOUNDED_FOLLOW_UP_REQUIRED`; Issue #34 owns the
  missing existing Wiki Drift/code-to-Wiki consumption seam after #15 merges.
