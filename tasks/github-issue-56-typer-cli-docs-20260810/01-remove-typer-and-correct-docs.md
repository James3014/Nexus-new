---
artifact_authority: current
owner: James Chen
status: ACTIVE
task_id: github-issue-56-remove-typer-correct-cli-docs
campaign_id: github-issue-56-typer-cli-docs-20260810
source_issue: https://github.com/James3014/Nexus-new/issues/56
AUTO_CHAIN: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
---

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
