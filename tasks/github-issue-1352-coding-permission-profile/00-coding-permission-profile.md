# Issue 1352 — Canonical Agy Coding Permission Profile and False-Completion Prevention

- task_id: `github-issue-1352-coding-permission-profile`
- campaign_id: `github-issue-1352-coding-permission-profile`
- status: `CANDIDATE`
- owner: `James Chen (James3014)`
- coordinator: `Antigravity Engineer`
- issue: `https://github.com/James3014/Nexus-new/issues/1352`
- durable_marker: `AGY_CODING_PERMISSION_PROFILE_ENFORCED`
- AUTO_CHAIN: `false`

## Objective

Prevent false-completion of Agy coding dispatches where the worker lacks necessary tool permissions (read/command/write) but exits with `COMPLETED / exit 0`. Establish:
1. Canonical effective-permission profile construction:
   - For `accept-edits`: bounded `read_file(<cwd>/**)`, explicit `write_file(<path>)` for authorized `--write-path` entries, and bounded `command(*)` when `--temp-command-permissions` is enabled.
   - Enforce least privilege with fixed non-overridable denies for destructive Git (`git push`, `git reset --hard`, `git clean`) and network tools (`gh`, `curl`, `wget`, `ssh`, `scp`, `rsync`).
2. Contradiction prevention (anti-blanket-override):
   - Exact write-path grants, repo read grants, and temporary command permissions must not coexist with blanket deny rules (`write_file(*)`, `read_file(*)`, `command(*)`) that silently neutralize the capability. Contradictory explicit user rules must fail closed before claim acquisition.
3. Deterministic permission preflight and readback:
   - Verify that the physical settings written to the leased account environment match the expected effective permission rules before execution.
   - Compute a deterministic SHA-256 hash (`permission_profile_sha256`) and category (`permission_profile_kind`: `CODING_BOUNDED`, `READ_ONLY_RESEARCH`, `NO_TOOL_PACKET`, `CUSTOM`).
4. Robust permission-refusal classification:
   - Classify all provider/model textual permission refusals or tool-denials during `accept-edits` as `PERMISSION_OR_SCOPE_ERROR` with non-zero exit code, never allowing false `COMPLETED / exit 0`.
5. Durable evidence projection:
   - Record `permission_profile_sha256`, `permission_profile_kind`, and effective permission summary in `operation.json` so controllers and workflow doctor can verify permission health.
6. Explicit security constants:
   - `TEMP_COMMAND_DENY`: `command(git push)`, `command(git reset --hard)`, `command(git clean)`, `command(gh)`, `command(curl)`, `command(wget)`, `command(ssh)`, `command(scp)`, `command(rsync)`.
   - `_UNSAFE_PERMISSION_RULES`: `command(*)`, `read_file(*)`, `write_file(*)`, `read_file(/)`, `write_file(/)`.

## Allowed Files

- `nexus/services/direct_operation_journal.py`
- `scripts/ops/nexus-agy-dispatch`
- `tests/services/test_agy_dispatch.py`
- `tasks/github-issue-1352-coding-permission-profile/00-coding-permission-profile.md`
- `tasks/github-issue-1352-coding-permission-profile/INDEX.md`

## Acceptance Criteria

1. Bounded coding profile (`accept-edits`) automatically includes exact write paths, repo-scoped read rule, and temp command permissions when requested, while excluding blanket denies.
2. Contradictory rules (e.g. `--temp-command-permissions` paired with `--deny "command(*)"`) fail closed with `CONTRADICTORY_PERMISSION_PROFILE` before lease acquisition.
3. Preflight readback verifies `settings.json` matches the intended effective profile before provider execution and records `permission_profile_sha256` and `permission_profile_kind` in the operation journal.
4. Semantic permission refusals and tool denials during `accept-edits` (including "permission denied", "tool execution permission block", "blocked by the active security/deny rules", "soft-denying tool confirmation", "headless mode cannot prompt for") cause non-zero exit and fail with `PERMISSION_OR_SCOPE_ERROR` / `HEADLESS_TOOL_PERMISSION_DENIED`.
5. True no-tool tasks (`mode="plan"`) without tool events can complete cleanly if no live permission denial occurred.
6. Destructive Git and network commands remain denied under coding profile.
7. Zero deletions to unrelated governance or configuration files.
8. Deterministic test suite, Ruff lint/format, and git diff check pass completely.

## Claim Ceiling

Source candidate and verified test suite only. No unilateral acceptance, merge, runtime activation, or release authority.
