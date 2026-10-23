# ARCHIVED 2026-10-24 (Phase-2 deletion, item 3)

Physical deletion of the experiment effect controller and its run guard: a complete design (#2454
fail-closed terminal wait, same-effect reconciliation, immutable artifacts) that was never wired
to any experiment entry point. Tracking issue: #2584 (stays open for the other items). Decision:
Owner (James), 2026-10-24, "兩批都照建議刪" (delete both batches as recommended; item 3: delete
the whole package), relayed by the coordinator, under the standing Phase-2 deletion approval of
2026-10-20. Plan v1 and the plan check (Codex) are on #2584. The originals are in git history at
`origin/main` 5de9b1f94baf9eff02a28f7ca2e5b7c382d3d829.

Evidence (the 10-20 evidence at 01dc1015, re-run on 5de9b1f94 before deleting):
- `git grep` of both module paths (dotted and slash) and every public name
  (`run_guarded_effect`, `ExperimentEffectController`, `ExperimentRunGuard`) over the whole tree:
  no caller outside the two modules and their own three test files; registry entries only in
  `tests/contracts/test_fail_closed_inventory.py` and `tests/golden_behavior/corpus.py` (GB-084);
- sibling repos nexus-core, nexus-runtime, nexus-learning, devspace, repo-learning,
  nexus-open-swe-runtime, repository-intelligence-engine, nexus-opencli-reviewer,
  nexus-workbench, nexus-deployment-lab and cairnwork (freshly fetched `origin/HEAD`): none;
- Mac mini and M4 `~/.local/bin` and `~/Library/LaunchAgents`: none;
- the live Gateway does not load either module.

## Deleted

| file | lines | callers on main |
| --- | --- | --- |
| `nexus/research/experiment_effect_controller.py` (`run_guarded_effect`, `ExperimentEffectController`) | 230 | none |
| `nexus/research/experiment_run_guard.py` (`ExperimentRunGuard`, `ExperimentRunContract`, `ExperimentRunLease`, `RunEffectConflict`, `write_immutable_artifact`) | 614 | only the controller |

No new orphan: the controller's only other import, `nexus.contracts.fail_closed.decide`, is still
used by `nexus.core.capability_executor_registry._exec_committee`.

## Registry edits

- `tests/contracts/test_fail_closed_inventory.py`: the `DECISION_PATHS` entry for
  `ExperimentEffectController._wait_for_terminal` is removed. `UNMIGRATED_BASELINE` is unchanged
  (it may only shrink); the site no longer exists, so the discovery scan has nothing to report.
- `tests/golden_behavior/corpus.py` GB-084 ("OUTCOME_UNKNOWN reconciles the same effect first"):
  the run-guard witness is removed. The two remaining witnesses run the live convergence path
  (`evaluate_gateway_convergence`) and assert `RECONCILE_RECOVERY`, the same `operation_id`,
  `request_id` and `idempotency_fence`, and `retry_authorized is False`, which covers both halves
  of the invariant.

## Tests

- Deleted (every case exercised deleted code): `tests/research/test_experiment_effect_controller.py`
  (5 tests), `tests/research/test_experiment_effect_fail_closed_2454.py` (3 tests),
  `tests/research/test_experiment_run_guard.py` (14 tests).
- Kept files keep every test id.
- New guard `tests/services/test_archived_phase2_item3_2026_10_24.py`: the modules (and `.py.bak`
  copies) stay absent and unimportable, nothing under `nexus/` or `scripts/` imports or names them,
  the fail-closed helper and its remaining decision path stay, and the scans flag every import and
  naming form (non-vacuous control).

## Restore

`git show 5de9b1f94:nexus/research/experiment_effect_controller.py` (and the other paths above).
Re-adding them fails the guard test on purpose; delete the guard in the same PR.
