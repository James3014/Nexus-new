# Task Card: remove orphan release facade

- artifact_authority: current
- task_id: `github-issue-147-remove-orphan-release-facade`
- source_issue: `#147`
- owner: James Chen
- status: ACTIVE
- baseline_revision: `1d6f7d163276b6b66381504c9a362505d4817a12`
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_push: true
- worker_may_approve: false
- worker_may_integrate: false
- `AUTO_CHAIN=false`

## Objective

Remove `AuditService.run_release` and `CliCommandsService.release`, which have
no caller or tests and import the nonexistent
`nexus.core.ops.nexus_release.perform_release` after emitting success-like
output. Preserve all current release gate/train surfaces unchanged.

## Inputs and dependencies

- Issue #147 and the fresh `RELEASE_BEHAVIORAL_OWNER_GATE` source/history audit.
- Current main at the baseline above.
- Evidence-backed Owner choice: deprecate/remove rather than invent release
  behavior or authority.

## Allowed files

- `nexus/services/audit_service.py`
- `nexus/services/cli_commands_service.py`
- `tests/services/test_audit_service.py`
- this card and campaign `INDEX.md`

## Forbidden scope

No release gate/train/control-plane behavior, CLI registration, compatibility
shim, replacement callable, tag, manifest, lock, route, lifecycle, approval,
integration, #191, or #143 change.

## Verification and evidence

- repository caller/registration search proves both methods have no consumer
- focused audit/facade/decomposition tests
- hostile assertion that neither facade exposes release and no missing import
  or success-like output remains
- Ruff check/format for changed Python files
- `git diff --check` and exact five-file scope audit

## Exit and block

Exit with exactly two method removals, focused tests, independent acceptance,
and terminal-success protected PR checks. `HARD_BLOCK` on a live caller or any
need to define release semantics.

Claim ceiling: `ORPHAN_RELEASE_FACADE_REMOVED_CANDIDATE_ONLY`.
