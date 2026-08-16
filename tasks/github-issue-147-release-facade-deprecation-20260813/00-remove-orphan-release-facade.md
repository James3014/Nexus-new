# Task Card: remove orphan release facade

- artifact_authority: current
- task_id: `github-issue-147-remove-orphan-release-facade`
- source_issue: `#147`
- owner: James Chen
- status: COMPLETE
- frontier_status: TERMINAL_RECONCILIATION
- baseline_revision: `1d6f7d163276b6b66381504c9a362505d4817a12` (historical baseline)
- reconciled_main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- current_main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- terminal_marker: `ORPHAN_RELEASE_FACADE_REMOVED_PROVEN`
- claim_ceiling: `ORPHAN_RELEASE_FACADE_REMOVED_PROVEN_ONLY`
- implementation_gate: `SATISFIED_BY_PR217_MERGE_9125913CA`
- commit_required: true
- candidate_required: true
- worker_may_commit: false
- worker_may_push: false
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

## Terminal Reconciliation

Implementation PR #217 MERGED 2026-08-12T18:26:33Z into `main`, head
`a2bc159b65a0f33a71405b1ed141cd2280876a03`, merge
`9125913ca809c954806386e3f11e6eb799ff882f`, ancestor of current main
`46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`. Issue #147 is CLOSED with
`state_reason=completed` (2026-08-12T18:26:56Z).

This card is terminally reconciled: `ORPHAN_RELEASE_FACADE_REMOVED_PROVEN` with
claim ceiling `ORPHAN_RELEASE_FACADE_REMOVED_PROVEN_ONLY` and
`AUTO_CHAIN=false`. The historical candidate-era claim ceiling
`ORPHAN_RELEASE_FACADE_REMOVED_CANDIDATE_ONLY` is preserved above. No
route/runtime/Workforce/approval/integration/release/production authority is
granted by this reconciliation.
