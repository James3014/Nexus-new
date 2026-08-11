---
artifact_authority: current
owner: James Chen
status: active
purpose: Synchronize the derived OpenWiki workflow table with the Issue #124 trusted anchor candidate.
issue: 126
---

## Objective

Add exactly the live `trusted-deletion-anchor.yml` workflow filename and its
verbatim top-level display name to the existing derived OpenWiki workflow
inventory table. Preserve all existing authority and claim ceilings.

## Inputs and dependencies

- Issue #126 complete body and comments.
- Reviewed Issue #124 candidate exact head:
  `1301514dba50587f25631c3b0a8d2ed0137be2d0`.
- Exact CI failure at PR #125 run `31455042645`:
  `tests.ops.test_openwiki_source_contract::test_openwiki_issue10_claims_match_current_inventory`
  with `assert 10 == 9`.
- `openwiki/INSTRUCTIONS.md`, including verbatim workflow-name and
  derived-non-authoritative rules.

## Allowed files

- `openwiki/workflows/github-actions.md`
- `tasks/github-issue-126-anchor-openwiki-sync-20260811/INDEX.md`
- `tasks/github-issue-126-anchor-openwiki-sync-20260811/01-sync-workflow-inventory.md`

File-count ceiling: one derived documentation file plus these two Task Card
files. The #126 commit must not change any Issue #124 workflow, module, or test
file.

## Forbidden scope

Do not regenerate unrelated OpenWiki pages. Do not modify workflow behavior,
`scripts/ops/select_tests.py`, `scripts/ops/pr_impact_gate.py`, tests, governed
Wiki, rulesets, Apps, lifecycle/Candidate/approval code, or cleanup surfaces.
Do not claim #104 complete, protected provenance, deletion authority, merge
authority, integration, release, production, or runtime truth.

## Required behavior

- Read `.github/workflows/trusted-deletion-anchor.yml` at the dependency head.
- Copy its filename and top-level `name:` value verbatim into the existing
  deterministic workflow inventory table.
- Preserve the page's `derived_non_authoritative` classification and existing
  structure; no stylistic rewrites.

## Verification

- `.venv/bin/pytest -q tests/ops/test_openwiki_source_contract.py::test_openwiki_issue10_claims_match_current_inventory`
- `.venv/bin/pytest -q tests/ops/test_trusted_deletion_anchor.py`
- YAML parse for `.github/workflows/trusted-deletion-anchor.yml`
- `.venv/bin/ruff check scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/ruff format --check --preview scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`
- `git diff --check`
- complete allowed-file, deletion, staged/unstaged stats, and staged-diff audit

## Evidence and exit criteria

The two focused suites pass; the exact #126 commit touches only the three
allowed paths; its parent is the reviewed #124 head; the successor PR binds
the exact card hash and ancestry and all current required CI is green. Any
additional file requirement is a `HARD_BLOCK`.

The worker may implement and commit only this scoped docs/Task-Card change.
Push, PR creation, review, merge, Issue closure, protected-proof claims, and
post-merge PR #118 activation remain with the primary agent/Owner authority.
