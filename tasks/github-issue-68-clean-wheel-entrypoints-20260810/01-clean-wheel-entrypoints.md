# Task Card: 01-clean-wheel-entrypoints.md

- issue: #68
- task_id: github-issue-68
- status: ACTIVE
- base_sha: 8f7c75ca08a6c88fad9b791f254d38d79ad8bf29
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

## Maximum Supportable Claim

The registered Nexus CLI and Cueline console entrypoints are importable and invoke their expected bounded surfaces from a clean installation of the exact Candidate wheel.
