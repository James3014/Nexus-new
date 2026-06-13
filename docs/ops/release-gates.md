# Nexus Release Gates & Branch Protection

This document defines the mandatory gates that must be passed before merging code or releasing new versions of Nexus.

## 🚦 Merge Gates (PR)

All Pull Requests to `main` or `master` must satisfy:

1. **Pytest Collect (P0)**: Suit must be discoverable.
2. **Changed-Files Lint (P1)**: No logic or style errors in touched Python files.
3. **Dependency Sync**: `uv lock --check` must pass.
4. **No Direct Push**: Workflows must not contain `git push` to protected branches.

## 📦 Release Blockers

The following conditions will block a release:

- **Dirty Worktree**: Uncommitted changes in submodules (e.g., `.tmp_build`).
- **Unexplained Deletions**: Files deleted without clear rationale in the PR/Commit message.
- **Unverified Claims**: Public README/PRD claims without machine-verifiable evidence.
- **Stale Receipt Trail**: Failure to generate capability receipts for core engine changes.

## 🛠️ Branch Protection Rules
- Require linear history.
- Require status checks to pass before merging.
- Disable direct force-push to `main`.

## 🌙 Artifact-Only Automation
Workflows like `Night Shift` and `Benchmark CI` are configured as **Artifact-Only**. They produce `.patch` files or `.jsonl` reports which must be manually reviewed and merged via the standard PR process. **Direct auto-commits are strictly forbidden.**
