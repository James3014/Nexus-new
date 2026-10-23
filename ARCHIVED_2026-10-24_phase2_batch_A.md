# ARCHIVED 2026-10-24 (Phase-2 deletion batch A)

Physical deletion of three unused service and integration entries: the operator outcome
receipt (`SelfHostedTaskService.record_operator_outcome` and its contract module), the
in-repo heartbeat loop `SelfHostedTaskService._heartbeat`, and the compatibility adapter
`TargetIntegrationLifecycle.transactional_integration` with its receipt type. Tracking issue:
#2584 (stays open for the other batches). Decision: Owner (James), standing Phase-2 approval of
2026-10-20 (DELETE-SAFE items only, one batch per PR, independent review and green required
checks). The originals are in git history at `origin/main`
f1e0594b36fe46eb2b98e8e359dc5d3db45f12a9.

Evidence: the per-symbol evidence for batch A was gathered at 01dc1015 (2026-10-20). It was
re-run on f1e0594b3 (2026-10-24) before deleting:
- `git grep` of every module path (dotted and slash), class, function and schema name over the
  whole tree (tests, docs and archives listed separately);
- sibling repos nexus-core, nexus-runtime, devspace, nexus-learning, nexus-open-swe-runtime,
  nexus-opencli-reviewer, repository-intelligence-engine, repo-learning, nexus-workbench,
  nexus-deployment-lab and cairnwork (local clones, freshly fetched `origin/HEAD`);
- Mac mini `~/Library/LaunchAgents`, `~/.local/bin`, crontab (none); M4 crontab,
  `~/Library/LaunchAgents`, `~/.local/bin` (read-only ssh);
- an import probe of the live Gateway deployment `a1-f1e0594b3` (deployment venv, `-I`,
  scratch cwd, `import scripts.ops.nexus_mcp_gateway_http` and
  `nexus.orchestrator.unified_mcp_gateway`, no server started);
- the live task state roots `~/.local/state/Nexus-new-self-hosted-state` and
  `~/.local/state/nexus-gateway`.

## Deleted

| # | item | lines | callers on main | sibling repos | schedules | live Gateway |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `nexus/orchestrator/self_hosted_task_service_parts/operator_outcome.py` (`_OperatorOutcomeMixin.record_operator_outcome`) | 209 | none; only the facade import and the class base list | none | none | module loaded (mixin base), method never called; no task state holds `operator_outcome_receipt(s)` |
| 1 | `nexus/contracts/operator_outcome_receipt.py` (`OperatorOutcomeReceipt`, `build_/validate_operator_outcome_receipt`) | 276 | only item 1 and two facade re-exports marked F401 | none | none | loaded only through item 1 |
| 2 | `SelfHostedTaskService._heartbeat` (`parts/checkpoint.py`) | 9 | none; no thread targets it | nexus-runtime has its own `coordinator._heartbeat` (the live loop) | none | method present, never called |
| 5 | `TargetIntegrationLifecycle.transactional_integration` | 113 | none (tests and the effect-owner registry only) | none | none | module loaded (service import), method never called |
| 5 | `IntegrationExecutionReceipt` (schema `nexus.transactional_integration_receipt.v1`) | 30 | only item 5 | none | none | never constructed |

Facade edits: `self_hosted_task_service.py` drops the two re-exports and the mixin base;
`checkpoint.py` drops the now-unused `json` and `threading` imports;
`target_integration_lifecycle.py` drops the now-unused `ControlledIntegrationManager` import.

## Kept (evidence correction and neighbours)

- `SelfHostedTaskService._touch_owned_state` stays. The 10-20 evidence said only `_heartbeat`
  called it; that was wrong since 15a5b6451 (2026-09-11):
  `runtime_coordination_bridge._State.heartbeat` calls it for every beat of nexus-runtime's loop.
- `read_projection.py` keeps hiding `operator_outcome_receipt(s)` from detailed snapshots, so a
  historical state that carries them stays private.
- `TargetIntegrationLifecycle.build_preview`, `authorize`, `cleanup_target`, `persist_receipt`
  and the rest of the class (live through `SelfHostedTaskService`).
- `_render_command` in `target_integration_lifecycle.py`: its only production user was
  `transactional_integration`; it is still pinned by the lexer round-trip test. Left for a
  separate decision (new orphan).

## Not in this batch

- Item 3 `experiment_effect_controller` + `experiment_run_guard` (REWIRE-OR-DELETE): Owner decision.
- Item 4a reconcile_recovery L499 (KEEP) and 4b L536 (DELETE-SAFE but only a rewrite of a
  2-line unreachable branch; not worth a deletion PR on its own).
- Item 6 `run_github_completion_loop` (REWIRE-OR-DELETE): Owner decision.
- Item 7 `gateway_deployment.validate_request` unreachable `gateway-recover` branch and duplicate
  hash domain: request validation in the deployer path counts as gate code under the standing
  approval, so it needs the Owner's explicit OK.

## Tests

- Deleted (every case exercised deleted code): `tests/contracts/test_operator_outcome_receipt.py`
  (8 tests), `tests/contracts/test_self_hosted_task_service_operator_outcome.py` (44 tests).
- Kept files keep every test id:
  - `tests/nexus/orchestrator/test_self_hosted_task_service.py`: the 11 `test_operator_outcome_*`
    cases assert the retirement; the snapshot-privacy case still seeds historical receipt fields
    and checks every read path hides them.
  - `tests/contracts/test_self_hosted_task_service_checkpoint.py`: the 7 heartbeat cases and the
    class-patch case drive the live beat (`runtime_coordination_bridge._State.heartbeat` ->
    `_mutate_state` -> `_touch_owned_state`); the member-table case asserts `_heartbeat` is gone.
  - `tests/nexus/orchestrator/test_target_integration_git_canary.py` (4 cases) and
    `test_target_integration_authority_closure.py` (9 cases): the authorized task state the
    adapter built is handed to the live sink `ControlledIntegrationManager.integrate_authorized_task_state`
    directly; every refusal (missing acceptance or authorization, candidate / task card / plan
    drift, expiry, dirty or untracked canonical, post-apply failure, verifier argv mismatch,
    merge conflict) now comes from the sink.
  - `tests/architecture/test_effect_owner_uniqueness.py`: `TARGET_LIFECYCLE_CALLER` relabelled
    RETIRED and removed from DECLARED / EDGES, so `integrate_authorized_task_state` has exactly one
    admitted caller (`SelfHostedTaskService.integrate_approved`).
  - `tests/architecture/fixtures/bigfile_split_class_tables.json`: two member rows removed.
- Added `tests/services/test_archived_phase2_batch_a_2026_10_24.py`: modules absent and
  `find_spec` None, members absent, no AST/importlib import or name under `nexus/` and `scripts/`
  (archive excluded), live neighbours present, non-vacuity. Mutation-checked: restoring the two
  modules and naming two retired symbols in `scripts/ops` gives 6 failures.

Not regenerated: `docs/plans/self_hosted_task_service_dependency_map.json` (already stale on base;
its regeneration test skips on base and head alike) and the generated `openwiki/` pages.
