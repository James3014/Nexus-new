# Task Card: 01-clean-wheel-entrypoints.md

- issue: #68
- task_id: github-issue-68
- status: COMPLETE
- reconcile_status: TERMINAL_RECONCILIATION
- base_sha: 8f7c75ca08a6c88fad9b791f254d38d79ad8bf29
- current_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- reconciled_main: 46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c
- marker: CLEAN_WHEEL_ENTRYPOINTS_IMPLEMENTED_AND_MERGED
- claim_ceiling: CLEAN_WHEEL_ENTRYPOINTS_IMPLEMENTED_AND_MERGED_ONLY
- merged_pr: #99
- merged_base: b025f86a0456d9a7c892368e0fd0fab6d0607614
- merged_head: cd0b6d82771acca6bd65113f772e1451187e704a
- merge_commit: e13ad5472296c8a303387f19662d19ce5a82bd0a
- worker: agy_flash
- provider: agy
- model: gemini-3.6-flash-high
- role: fast_bounded_implementation
- autonomy: L2
- context: nexus_bounded
- AUTO_CHAIN: false

## Objective

Fix registered console entrypoints (`nexus` and `nexus-cueline-worker`) when installed from a clean wheel environment so they can import their entrypoint modules without `ModuleNotFoundError: No module named 'scripts'`.

## Allowed Files (Packaging & Layout fix)

1. `pyproject.toml`
2. `scripts/__init__.py`
3. `tests/ops/test_clean_wheel_entrypoints.py`

Task Card authority artifacts in `tasks/github-issue-68-clean-wheel-entrypoints-20260810/` do not count towards the implementation file ceiling.

## Forbidden Scope

- CLI framework migration (e.g. Typer / Click changes)
- New CLI commands
- Subsystem refactoring
- Unrelated dependency cleanup
- OpenWiki cleanup

## Mandatory Verification Commands

1. Build wheel and sdist in isolated venv/tmp.
2. Install built wheel into clean virtual environment without repository PYTHONPATH.
3. Run `nexus --help` (must exit code 0).
4. Run `nexus-cueline-worker --help` or invoke stdin validation surface (must not fail with `ModuleNotFoundError: No module named 'scripts'`).
5. Run focused packaging/CLI tests.
6. `git diff --check`

## Acceptance Criteria

1. `nexus --help` exits 0 from isolated installed wheel env.
2. `nexus-cueline-worker` reaches stdin validation surface from isolated installed wheel env without `ModuleNotFoundError`.
3. Focused tests pass.
4. `git diff --check` clean.

## Candidate Requirements

- Branch: `agy/issue-68-clean-wheel-entrypoints`
- Candidate PR created
- Receipt recorded with base SHA, Task Card SHA-256, Workforce Admission binding, Candidate SHA, wheel identity, isolated env test output, verification commands/results, claim ceiling
- No self-approve, no self-merge

## Terminal Reconciliation Receipt

- Issue #68: CLOSED, state_reason=completed (2026-08-11); PR #99: MERGED (merge commit `e13ad5472296c8a303387f19662d19ce5a82bd0a`, base `b025f86a0456d9a7c892368e0fd0fab6d0607614`, head `cd0b6d82771acca6bd65113f772e1451187e704a`), 4 files / +137 / -1
- Physical change: `pyproject.toml` includes the `scripts` package; focused clean-wheel test `tests/ops/test_clean_wheel_entrypoints.py`
- Verified at merge head: focused clean-wheel test 1 passed; Ruff check and preview format pass; `git diff --check` pass; all five GitHub exact-base required gates pass
- Current main readback: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`; both card blobs byte-identical to the PR #99 merge
- This card records a historical implementation receipt only. It grants no runtime/route/Workforce/provider/approval/integration/merge/release/production authority. AUTO_CHAIN=false.

## Maximum Supportable Claim

The registered Nexus CLI and Cueline console entrypoints are importable and invoke their expected bounded surfaces from a clean installation of the exact wheel, as physically merged via PR #99 into Nexus-new main. Repository-contained packaging/source/test receipt only; no production/release claim.
