# Task Card: remove six archived legacy adapters

- artifact_authority: current
- task_id: `github-issue-52-legacy-adapters`
- source_issue: `#52`
- owner: James Chen
- status: ACTIVE
- baseline_revision: `069596056fff852bad8c826725902d25361aa9c7`
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_push: true
- worker_may_approve: false
- worker_may_integrate: false
- `AUTO_CHAIN=false`

## Objective

Delete six explicitly archived `scripts/legacy` adapters with no current caller
and remove exactly their six stale `muse_nexus.egg-info/SOURCES.txt` rows. Add
no replacement, shim, alias, caller adaptation, or behavior change.

## Inputs and dependencies

- Issue #52, including Owner comments `5236520101`, `5247876669`, and
  `5252950958`.
- Current main `c994b24c57c1ad7cfec1cb407074995925e7deb6`.
- #54 is closed; #55 has no branch/PR and is serialized after this Candidate.
- Fresh exact-path/module/dynamic-import/entrypoint and packaging preflight.

## Allowed files

- `scripts/legacy/git_manager.py` (delete)
- `scripts/legacy/linter.py` (delete)
- `scripts/legacy/llm_client.py` (delete)
- `scripts/legacy/patcher.py` (delete)
- `scripts/legacy/reporter.py` (delete)
- `scripts/legacy/workspace_manager.py` (delete)
- `muse_nexus.egg-info/SOURCES.txt` (remove exactly six rows)
- `docs/testing/test_impact_map.md` (add exact six adapter impact mappings)
- `tests/ops/test_issue52_cleanup_impact_map.py` (assert mappings and fallback)
- this card and campaign `INDEX.md`

## Forbidden scope

No active `nexus.services.*`, callers, dependencies, entry points, historical
reports, other inventory rows, compatibility surfaces, #55 implementation,
#191, or #143. The impact-map amendment is documentation/test-selector scope
only; it does not add a replacement or alter runtime behavior. If any live
caller or packaging requirement appears, stop rather than adapting it.

## Verification

- exact path/module/import/entrypoint searches before and after deletion
- focused Git/Linter/Gateway/Patcher/Reporter/Workspace/migration/CLI tests
- `uv build` and archive/source-inventory absence checks
- `uv run ruff check` on affected current test/service surfaces
- `git diff --check` and exact deletion/inventory/impact-map audit

## Exit, block, and residual debt

Exit only with exact eleven-file scope (six deletions, one inventory edit, two
impact-map/test files, and two governance files), package artifacts excluding
all deleted paths, focused tests, independent acceptance, and protected PR
checks. `HARD_BLOCK` on any caller, unexpected inventory change, overlap, or
scope widening. PR #87 becomes superseded only after this fresh Candidate is
physically established.

Claim ceiling: `SIX_ARCHIVED_CALLER_FREE_ADAPTERS_REMOVED_CANDIDATE_ONLY`.
