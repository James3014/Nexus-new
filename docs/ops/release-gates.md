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

## 🔭 Live Gateway Source Drift Check (#1900)
Owner decision (#1900, 2026-10-12): the live MCP Gateway may run only commits published on GitHub `main`, or an exact head of an open/merged PR during a bounded rebind. `scripts/ops/check_gateway_source_drift.py` is a **read-only** detector for that rule. It reads `http://127.0.0.1:8766/health`, finds the newest ancestor of the loaded `git_head` on `origin/main` (it runs `git fetch origin main` in `--repo`, or uses `--main-ref` without fetching), and reports `GATEWAY_SOURCE_UNPUBLISHED(n)` (ALERT; an unpublished loaded head where at least one unpublished commit touches a path outside `tasks/` — the JSON lists the touched paths) or, when EVERY unpublished commit touches only `tasks/` paths (Owner refinement, #1900, 2026-10-13: a merge commit is judged by its diff against its first parent), the INFO `GATEWAY_BIND_ONLY_LOCAL_COMMITS(n)` (exit 0, still lists the paths; root cause tracked in #1939), and `GATEWAY_BEHIND_MAIN(n)` (WARN when more than 50 commits or more than 7 days behind; below that, OK). An unreachable or malformed health payload fails closed (`GATEWAY_HEALTH_UNREACHABLE` / `GATEWAY_HEALTH_MALFORMED`). Exit codes: 0 OK/INFO, 1 WARN/ALERT, 2 probe failure. Run it with `python scripts/ops/check_gateway_source_drift.py --repo <Nexus-new clone> [--json] [--offline]`; `--report-issue 1900` (only when passed explicitly) creates or edits one comment tagged `<!-- GATEWAY_DRIFT_REPORT -->`. To schedule it, an operator may add a user LaunchAgent whose `ProgramArguments` run that command with `--report-issue 1900` and a `StartInterval` (for example 21600 seconds), `StandardOutPath`/`StandardErrorPath` under `~/Library/Logs/`; agents must not install it themselves. The check never reloads or rebinds the Gateway: remediation is a rebind through the #526 governed path and is an Owner decision.
