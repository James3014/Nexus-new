---
artifact_authority: current
owner: James Chen
status: COMPLETE
terminal_state: TERMINAL_RECONCILIATION
purpose: Synchronize the derived OpenWiki workflow inventory and its exact count assertion.
issue: 126
supersedes: 01-sync-workflow-inventory.md
---

## Objective

Synchronize the existing derived OpenWiki workflow table/count prose and the
exact source-contract count expectation with the inherited Issue #124 trusted
anchor candidate. Preserve all authority and claim ceilings.

## Inputs and dependencies

- Issue #126 body and CONTRACT_DELTA comment.
- Reviewed Issue #124 candidate exact head:
  `1301514dba50587f25631c3b0a8d2ed0137be2d0`.
- Exact PR #125 impact run `31455042645`, which proved the live workflow count
  increased from 9 to 10.
- Card 01 execution, which added only the exact row but reproduced the stale
  hard-coded `len(workflow_files) == 9` expectation and made no red commit.
- `openwiki/INSTRUCTIONS.md` verbatim workflow-name and
  derived-non-authoritative rules.

## Allowed files

- `openwiki/workflows/github-actions.md`
- `tests/ops/test_openwiki_source_contract.py`
- `tasks/github-issue-126-anchor-openwiki-sync-20260811/INDEX.md`
- `tasks/github-issue-126-anchor-openwiki-sync-20260811/01-sync-workflow-inventory.md`
- `tasks/github-issue-126-anchor-openwiki-sync-20260811/02-sync-workflow-inventory-contract.md`

File-count ceiling: two implementation/test files plus these three Task Card
files. The implementation commit must not change any Issue #124 workflow,
module, or hostile-test file.

## Forbidden scope

Do not regenerate unrelated OpenWiki pages. Do not change any assertion except
the two exact workflow-count expectations in
`test_openwiki_issue10_claims_match_current_inventory`. Do not add skip, xfail,
dynamic bypass, relaxed matching, or test deletion. Do not modify workflow
behavior, `scripts/ops/select_tests.py`, `scripts/ops/pr_impact_gate.py`,
governed Wiki, rulesets, Apps, lifecycle/Candidate/approval code, or cleanup.
Do not claim #104 complete, protected provenance, deletion authority, merge
authority, integration, release, production, or runtime truth.

## Required behavior

- Copy the inherited workflow filename and top-level `name:` verbatim into the
  existing table.
- Update only the page's workflow count prose from 9 to 10.
- Update only `len(workflow_files) == 9` to `== 10` and the matching
  `all 9 GitHub Actions workflows` assertion to `all 10`.
- Preserve all other source-contract assertions and page structure.

## Verification

- `.venv/bin/pytest -q tests/ops/test_openwiki_source_contract.py`
- `.venv/bin/pytest -q tests/ops/test_trusted_deletion_anchor.py`
- YAML parse for `.github/workflows/trusted-deletion-anchor.yml`
- `.venv/bin/ruff check tests/ops/test_openwiki_source_contract.py scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/ruff format --check --preview tests/ops/test_openwiki_source_contract.py scripts/ops/trusted_deletion_anchor.py tests/ops/test_trusted_deletion_anchor.py`
- `.venv/bin/python -m compileall -q tests/ops/test_openwiki_source_contract.py`
- `git diff --check`
- complete allowed-file, deletion, staged/unstaged stats, and staged-diff audit

## Evidence and exit criteria

Both complete focused modules pass; the exact implementation commit changes
only the docs and source-contract test; the Task Card supersession is committed
separately; the successor PR preserves the reviewed #124 ancestor, binds the
new card blob hash, passes all current required CI, and receives independent
exact-head review. Any further file requirement is a `HARD_BLOCK`.

The worker may implement and commit only the two scoped files. Push, PR
creation, review, merge, Issue closure, protected-proof claims, and post-merge
PR #118 activation remain with the primary agent/Owner authority.

## Terminal reconciliation

Completed by PR #127 exact head `6d1eb2bf39db537a3f0714dda77ba0c290da11cf`,
merge `fffc127cb`, required checks successful, reconciled on current `main`
`12ff821a3aedfa4c5ee3f6f89b2780ccbc0fc601`. Historical workflow-count delta
`9` -> `10` remains effective. Markers: `BOOTSTRAP_ANCHOR_INSTALLED`,
`OPENWIKI_INVENTORY_SYNCHRONIZED`; ceiling: `NO_PROTECTED_PROVENANCE_CLAIM`;
`AUTO_CHAIN=false`.
