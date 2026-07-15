# Nexus Testing Runbook

This runbook defines the validation gates and CI procedures for Nexus.

## 🛡️ CI Validation Gates

### 1. Pytest Collect Gate (P0)
Ensures that all tests are discoverable and there are no syntax or import errors in the test suite.
- **Command**: `uv run pytest tests/ --collect-only -q`
- **When**: Pre-commit, CI.

### 2. Lint Gate (P1)
Enforces code style and catches logic errors in changed files.
- **Modes**:
  - **PR-safe**: Compares against `origin/main`. Used in Pull Requests.
  - **Commit-safe**: Compares against `HEAD~1`. Used in direct pushes.
- **Filter**: `--diff-filter=ACMR` (only active/modified files, excludes deleted).
- **Command**: `uv run ruff check <files>`

### 3. Pytest Execution Gate (P1)
Runs the test suite with fail-fast mode enabled.
- **Command**: `uv run pytest tests/ -x -v --timeout=300`
- **Artifacts**: Produces `pytest-stdout.log` and `pytest-report.xml` on failure.

---

## 🛠️ Local Verification Recipes

### Wiki CI, Release, and Operational Gate

Run the same blocking gate locally and before release:

```bash
uv run python scripts/ops/wiki_ci_release_gate.py --check --output-dir .nexus/reports/wiki-governance
```

The command emits a commit-bound receipt and evidence file. Critical artifact,
identity, authority, coverage, current-link, freshness, and Knowledge Agent
runtime failures return non-zero. Governed legacy or intentional placeholder
debt is reported as warning data and cannot turn a blocked critical gate into a
pass.

### Workflow YAML Check
Before pushing changes to `.github/workflows/`, verify YAML syntax:
```bash
# Using actionlint if available
actionlint .github/workflows/*.yml
```

### Full Pre-delivery Smoke
```bash
uv lock --check
uv run pytest tests/ --collect-only -q
# Check current commit diff for lint
uv run ruff check $(git diff --name-only --diff-filter=ACMR HEAD~1...HEAD -- '*.py')
```

---

## ⚠️ Forbidden Actions
- **Direct Push to main**: Avoid using workflows that automatically commit to `main`. Use artifacts instead.
- **Staging `.tmp_build`**: This directory is for internal build state and must never be committed.
- **Build-time Model Downloads**: Docker builds must remain lightweight; models should be provided at runtime.
