---
artifact_authority: current
owner: James Chen
status: COMPLETE
task_id: github-issue-56-remove-typer-correct-cli-docs
campaign_id: github-issue-56-typer-cli-docs-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/56
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
frontier_status: TERMINAL_RECONCILIATION
terminal_marker: ISSUE_56_PRODUCT_COMPLETE_STALE_CARD_ONLY_PROVEN
claim_ceiling: ISSUE_56_PRODUCT_COMPLETE_STALE_CARD_ONLY_PROVEN_ONLY
historical_baseline: 14dd1f29183b09646215462b97b0dd0feb8c0743
pr70_base: 84eaa6886e0388a4e15f5b837c89e37768b14307
pr70_head: 40c37dc5eed5a72199c373ea3e21bd51bf9462bc
pr70_merge: 4e785930eb67ea973a9917c906561c1c86946595
historical_reconciled_main: cdf2570ede5ae218f36f886b696c8da45458043a
reconciled_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
current_main: 71ae533ec9f795477131645f96cea1c93b4f4d40
---

Historical source-PR current-main binding: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; retained as historical evidence after the Issue #428 active rebind.

# Remove Direct Typer Contract and Correct CLI/Cueline Docs

## Objective

Remove the unused direct Typer dependency, regenerate the lockfile, and make
the current OpenWiki CLI/Cueline page describe only observed Click commands and
the stdin/subprocess worker contract. Do not change runtime behavior.

## Baseline

- GitHub main: `14dd1f29183b09646215462b97b0dd0feb8c0743`
- fresh re-anchor comment: https://github.com/James3014/Nexus-new/issues/56#issuecomment-5234633922

## Allowed files

- `pyproject.toml`
- `uv.lock`
- `openwiki/runtime/cli-and-cueline.md`

Maximum changed files: 3. Task Card files are authorization artifacts.

## Required change

- prove first-party executable surfaces contain zero Typer imports;
- remove only `typer>=0.9.0,<1.0.0` from direct dependencies;
- regenerate `uv.lock` deterministically; never hand-edit it;
- retain transitive Typer required by current third-party packages;
- correct only stale framework, nonexistent command, and Cueline polling/
  SanitizedRunner claims on the named OpenWiki page.

## Verification

- `uv lock --check` and a clean frozen sync;
- build wheel and sdist; invoke registered CLI entry points/help;
- focused CLI, Cueline, packaging, dependency and documentation drift tests;
- verify actual help output against documented commands;
- full exact-base/post-change regression comparison;
- Ruff where applicable and `git diff --check`.

## Forbidden scope

No Click migration, runtime/CLI/Cueline behavior edit, benchmark fixture edit,
other dependency cleanup, generated report, authority/lifecycle/route/workforce
change, direct main push, or merge.

## Exit

The three-file bounded diff passes lock/build/help/test checks, preserves
transitive dependency truth, and receives independent exact-commit review.

## Block class

`RECOVERABLE_BLOCK` for lock/docs/test defects. `HARD_BLOCK` if current
first-party code actually imports Typer or requires it as a direct API contract.

## Physical evidence and terminal boundary

- Issue #56 is closed `completed` (2026-08-10).
- PR #70 merged 2026-08-10: head
  `40c37dc5eed5a72199c373ea3e21bd51bf9462bc` onto base
  `84eaa6886e0388a4e15f5b837c89e37768b14307` as
  `4e785930eb67ea973a9917c906561c1c86946595`; exact delivered product scope:
  `pyproject.toml`, `uv.lock`, `openwiki/runtime/cli-and-cueline.md` plus the
  Task Card pair; five changed files, zero deletions.
- Owner receipt `issuecomment-5253052085`
  (`POST_MERGE_RECONCILIATION_20260811`): `PRODUCT_COMPLETE / STALE_CARD_ONLY`;
  exact-base Bandit/Pyright/Ruff/impact/Wiki gates passed; Tier 3 skipped;
  transitive Typer may remain by design.
- Current main `71ae533ec9f795477131645f96cea1c93b4f4d40` readback: PR #70 merge
  `4e785930...` and head `40c37dc5...` are ancestors
  (`git merge-base --is-ancestor`); `pyproject.toml` contains no direct Typer
  declaration; `openwiki/runtime/cli-and-cueline.md` contains no Typer or stale
  command/Cueline claim.

`ISSUE_56_PRODUCT_COMPLETE_STALE_CARD_ONLY_PROVEN` is limited to the exact
GitHub collaboration cleanup at the merged PR #70 head. It grants no product,
runtime, route, Workforce, lifecycle, Candidate, approval, integration, merge,
release, or production authority. `AUTO_CHAIN=false`.
