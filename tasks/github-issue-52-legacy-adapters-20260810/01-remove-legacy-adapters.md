---
id: 01-remove-legacy-adapters
campaign_id: github-issue-52-legacy-adapters-20260810
status: active
source_issue: https://github.com/James3014/Nexus-new/issues/52
baseline_main: 84eaa6886e0388a4e15f5b837c89e37768b14307
block_class: RECOVERABLE_BLOCK
---

# 01 — Remove six archived scripts/legacy adapters

## Objective

Delete the six self-archived `scripts/legacy` adapters whose callers no
longer exist, and remove only their six exact stale
`muse_nexus.egg-info/SOURCES.txt` rows. Add no replacement adapter, shim,
feature, or redesign.

## Authorized files

- `scripts/legacy/git_manager.py`
- `scripts/legacy/linter.py`
- `scripts/legacy/llm_client.py`
- `scripts/legacy/patcher.py`
- `scripts/legacy/reporter.py`
- `scripts/legacy/workspace_manager.py`
- `muse_nexus.egg-info/SOURCES.txt` (only the six exact rows above)
- this card + `INDEX.md`

## Forbidden scope

- any active `nexus.services.*` implementation
- historical reports (incl. `full_workspace_xray.md`)
- `muse_nexus.egg-info` directory-wide cleanup
- engine unreachable-path cleanup
- dependency changes
- `nexus/services/nexus_probe.py` (not in this Issue scope)
- direct `main` push or self-merge
- compatibility aliases or callers adaptation

## Inputs

- fresh `main` at `84eaa6886` (PR #70/#71 do not overlap these paths or
  SOURCES.txt)
- prior #52 card/governance commit not physically recoverable; this new
  durable card is the binding authority artifact

## Controls

1. Re-anchor to fresh `main` before deletion (done: branch created from
   `84eaa6886`).
2. Bind exact Git-tracked Task Card before deletion (this card).
3. Rerun exact path/module/symbol/importlib/entrypoint/caller and packaging
   searches before and after deletion.
4. If any current caller, dynamic import, entry point, or packaging
   requirement exists for a path, remove that path from scope and stop.
5. Do not serialize with #54/#55 on SOURCES.txt (both complete before this
   card mutates it).

## Verification

1. Repeat exact path/module/symbol searches pre/post deletion: zero refs
   outside historical scanner output and generated packaging inventory.
2. Run active Git, Linter, Gateway/LLM, patcher, reporter, workspace,
   migration-validator, packaging, and CLI tests selected from current
   callers.
3. Build/install package from exact branch and prove deleted files absent
   from produced source inventory.
4. Full exact-base vs post-deletion regression comparison; no new failure.
5. Ruff on affected current surfaces and `git diff --check`.

## Exit criteria / maximum claim

Six archived adapters with zero current callers were deleted and the
generated source inventory was reconciled, without changing active
behavior. Terminal marker `LEGACY_ADAPTER_REMOVAL_PROVEN`.

## Completion receipt

- Task Card authorization commit: `f1e9139b0` (card SHA-256
  `a6d2b569edeca38c2e099b4b574896e6b5b3bc198234b592afcab23101eef021`)
- implementation head: `4b456a642`
- PR: https://github.com/James3014/Nexus-new/pull/87
- deleted the six archived `scripts/legacy` adapters (all carry the
  `LEGACY / ARCHIVED SCRIPT` marker; zero callers/dynamic-imports/CLI
  entrypoints/module refs outside historical scanner output and generated
  packaging inventory)
- removed exactly the six stale `muse_nexus.egg-info/SOURCES.txt` rows
  (previously lines 425-430); no other SOURCES.txt change
- replacement surfaces verified present: `nexus.services.git.GitManager`,
  `nexus.services.linter.Linter`, `nexus.services.gateway.BattlesuitGateway`,
  `nexus.services.local_heal.patcher.Patcher`,
  `nexus.services.reporter.Reporter`,
  `nexus.services.workspace.WorkspaceManager`
- post-deletion searches rerun: zero references to the deleted paths in
  source, tests, CLI, pyproject, or dynamic imports (only the Issue card and
  historical `full_workspace_xray.md`, both exempt)
- build/install via `uv build`: wheel + sdist contain zero `scripts/legacy`
  entries; produced `SOURCES.txt` has zero legacy rows
- focused Git/Linter/Patcher/Workspace/Gateway/Reporter/LocalHeal/CLI tests:
  84 passed (candidate), base identical (0 fails) — zero regression
- Ruff affected current surfaces: identical pre-existing findings on base
  (zero net-new); `git diff --check` clean
- reached `CANDIDATE_PR_READY` (PR opened to `main`; no self-approve/merge)
