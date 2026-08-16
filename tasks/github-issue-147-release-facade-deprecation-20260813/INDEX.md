# Issue #147 Release Facade Deprecation

- artifact_authority: current
- owner: James Chen
- status: COMPLETE
- frontier_status: TERMINAL_RECONCILIATION
- source_issue: `#147`
- baseline_main: `1d6f7d163276b6b66381504c9a362505d4817a12` (historical baseline)
- reconciled_main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- current_main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- current_frontier: `00-remove-orphan-release-facade.md`
- completed_cards:
  - `00-remove-orphan-release-facade.md`
- blocked_cards: `[]`
- terminal_marker: `ORPHAN_RELEASE_FACADE_REMOVED_PROVEN`
- claim_ceiling: `ORPHAN_RELEASE_FACADE_REMOVED_PROVEN_ONLY`
- implementation_gate: `SATISFIED_BY_PR217_MERGE_9125913CA`
- worker_may_commit: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- `AUTO_CHAIN=false`

This campaign removes an orphan facade that imports a nonexistent release
implementation. It does not own or alter the existing release gate/train.

## Terminal Reconciliation

Issue #147 is CLOSED with `state_reason=completed` (2026-08-12T18:26:56Z).
Implementation PR #217 MERGED 2026-08-12T18:26:33Z into `main`, head
`a2bc159b65a0f33a71405b1ed141cd2280876a03`, merge
`9125913ca809c954806386e3f11e6eb799ff882f`, ancestor of current main
`46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`.

Current main physical evidence: `AuditService.run_release` and
`CliCommandsService.release` are absent from
`nexus/services/audit_service.py` / `nexus/services/cli_commands_service.py`,
and the hostile test `test_orphan_release_facades_are_not_exposed` is present
at `tests/services/test_audit_service.py:188`.

This reconciliation proves only the repository-contained orphan release facade
removal source/tests. It does not authorize route, runtime, Workforce,
approval, integration, release, or production authority. `CapabilityPlanner`
remains sole route/capability selection authority.
