# Issue 1359 — Agy Command Channel Write-Scope Enforcement and Transient Mutation Prevention

- task_id: `github-issue-1359-command-channel-write-scope`
- campaign_id: `github-issue-1359-command-channel-write-scope`
- status: `CANDIDATE`
- owner: `James Chen (James3014)`
- coordinator: `Antigravity Engineer`
- issue: `https://github.com/James3014/Nexus-new/issues/1359`
- durable_marker: `AGY_COMMAND_WRITE_SCOPE_ENFORCED`
- AUTO_CHAIN: `false`

## Objective

Prevent Agy coding operations (`accept-edits`) from mutating or reverting files outside their declared `--write-path` scope via the command channel (`command(*)`). Establish:
1. Hardened Command Deny Rules (`TEMP_COMMAND_DENY`):
   - Prohibit Git commands that alter index or worktree state across the repository: `git checkout`, `git restore`, `git stash`, `git reset`, `git clean`, `git commit`, `git branch`, `git merge`, `git rebase`, `git cherry-pick`, `git revert`.
   - Preserve existing destructive and network deny rules: `git push`, `gh`, `curl`, `wget`, `ssh`, `scp`, `rsync`.
   - Read-only Git commands (`git status`, `git diff`, `git log`, `git show`, `git rev-parse`) and execution tools (`pytest`, `python`, `uv`, `ruff`, etc.) remain fully functional.
2. Exact Write-Scope Verification at Terminalization:
   - For `accept-edits` operations with declared `write_paths`, verify that `observed_changed_paths` contains only paths matching authorized write paths.
   - Any modification to an unauthorized file (including pre-existing dirty files outside write scope) fails closed with `PERMISSION_OR_SCOPE_ERROR` and failure kind `SCOPE_VIOLATION_UNAUTHORIZED_MUTATION`, rejecting `exit 0`.
3. Pre-Existing Dirty State Preservation:
   - Pre-existing uncommitted files outside declared `write_paths` must remain byte-identical across the entire dispatch lifecycle (verified via source baseline SHA-256 fingerprinting).
4. Durable Journal Projection:
   - Record `write_paths`, `scope_validation_state` (`VERIFIED_IN_SCOPE`, `VIOLATION_OUT_OF_SCOPE`, `UNCONSTRAINED`), and `scope_violations` in the direct operation journal.
5. Deterministic G0 RED Fixture:
   - Freeze a deterministic fixture with one pre-existing dirty sentinel outside write scope and one authorized target, reproducing the command-channel reversion attempt and proving the bounded mutation guard blocks it.

## Allowed Files

- `nexus/services/direct_operation_journal.py`
- `scripts/ops/nexus-agy-dispatch`
- `tests/services/test_agy_dispatch.py`
- `tasks/github-issue-1359-command-channel-write-scope/00-command-channel-write-scope.md`
- `tasks/github-issue-1359-command-channel-write-scope/INDEX.md`

## Acceptance Criteria

1. `TEMP_COMMAND_DENY` contains explicit deny rules for `command(git checkout)`, `command(git restore)`, `command(git stash)`, `command(git reset)`, `command(git clean)`, `command(git commit)`, `command(git branch)`, `command(git merge)`, `command(git rebase)`, `command(git cherry-pick)`, `command(git revert)`, `command(git push)`, `command(gh)`, `command(curl)`, `command(wget)`, `command(ssh)`, `command(scp)`, `command(rsync)`.
2. Attempts to execute `git checkout`, `git restore`, `git stash`, or `git reset` are denied before mutation can occur.
3. Read-only Git commands (`git status`, `git diff`, `git log`, `git show`, `git rev-parse`) and execution commands remain permitted and usable.
4. Bounded `accept-edits` operations modifying only declared write paths succeed cleanly with `scope_validation_state=VERIFIED_IN_SCOPE`.
5. Bounded `accept-edits` operations with out-of-scope mutations fail closed with exit code 1, `failure_kind=SCOPE_VIOLATION_UNAUTHORIZED_MUTATION`, and `scope_validation_state=VIOLATION_OUT_OF_SCOPE`.
6. Pre-existing dirty sentinels outside declared write paths remain byte-identical throughout execution.
7. Operation journal durability: `write_paths`, `scope_validation_state`, and `scope_violations` are persisted and exposed in public operation view.
8. Deterministic test suite, Ruff lint/format, and git diff check pass completely.

## Claim Ceiling

Source candidate and verified test suite only. No unilateral acceptance, merge, runtime activation, or release authority.
