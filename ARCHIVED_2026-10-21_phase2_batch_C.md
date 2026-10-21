# ARCHIVED 2026-10-21 (Phase-2 deletion batch C)

Physical deletion of unused verifier, gate and guardrail prototypes: most of
`nexus/verifiers/domain`, two domain verifier packs, a replay dashboard, a challenge harness, the
`nexus/engine/verifiers` refactor guard, `nexus/oracle/promote.py`, the `nexus/gate` package and
the `nexus/guardrails` package. Tracking issue: #2584 (stays open for the other batches).
Decision: Owner (James), standing Phase-2 approval of 2026-10-20 (DELETE-SAFE items only, one batch
per PR, independent review and green required checks), confirmed 2026-10-21 with 「好，開始做 #2584
刪除」. The originals are in git history at `origin/main`
32f9e1907915b8f056467127a093eb754bb0f7a1.

Evidence: per-symbol evidence for batch C gathered at 01dc1015 (2026-10-20). It was re-run on
32f9e1907 before deleting:
- `git grep` of every module path (dotted and slash), class/function name and
  `importlib`/`import_module`/`__import__`/`find_spec` literal over `nexus/`, `scripts/`,
  `.github/`, `pyproject.toml`, `Makefile` and config files (tests, docs and archives listed
  separately);
- the sibling repos nexus-core, nexus-runtime, devspace, nexus-learning, nexus-open-swe-runtime,
  nexus-opencli-reviewer, repository-intelligence-engine, repo-learning, nexus-workbench,
  nexus-deployment-lab (local clones, HEAD) and cairnwork (fresh clone of `main` add5ee1): no hits;
- `~/Library/LaunchAgents`, `~/.local/bin` and crontab on the M4: no hits (the Mac mini was checked
  at evidence time).

What the re-run found:
- No non-test importer outside the batch. The only importers were inside the batch:
  `replay_dashboard` and the two packs import `name_sanity` / `inheritance` / `django_semantic`;
  `challenge_harness` imports `astropy_pack`; `experimental_gate` imports `gate_judge`;
  `refactor_guard` imports `engine/verifiers/base.py`, which has no other user.
- `nexus.gate` is not `nexus.gateway`: every `nexus.gate` text hit outside the package is a
  `nexus.gateway.*` name, wiki prose or an archived script
  (`scripts/archive/2026-10/bench/run_observation_cycle_0*.py`). No live gate or governance
  path imports it. The live gates are in `nexus/governance` and Core.
- The string `name_sanity` in `nexus/selection/score_aggregator.py` is a weight-table key that is
  matched against verdict names. It does not load the module.
- `scripts/governance/freeze_v27_2.py` and `generate_taxonomy.py` mention these files only in
  prose strings.

## Modules (29 files, 1,150 lines)

| path | lines |
|---|---:|
| `nexus/verifiers/domain/astropy/__init__.py` | 0 |
| `nexus/verifiers/domain/astropy/astrophysics_guard.py` | 65 |
| `nexus/verifiers/domain/astropy/fits_reader.py` | 4 |
| `nexus/verifiers/domain/astropy/unit_normalizer.py` | 2 |
| `nexus/verifiers/domain/django/__init__.py` | 0 |
| `nexus/verifiers/domain/django/django_core_logic_guard.py` | 80 |
| `nexus/verifiers/domain/django/django_migration_guard.py` | 73 |
| `nexus/verifiers/domain/django/django_migration_guard.py.bak` | 62 |
| `nexus/verifiers/domain/django_semantic.py` | 33 |
| `nexus/verifiers/domain/inheritance.py` | 27 |
| `nexus/verifiers/domain/name_sanity.py` | 38 |
| `nexus/verifiers/domain/common_core/lock_helpers.py` | 12 |
| `nexus/verifiers/domain/concurrency/buggy_targets.py` | 71 |
| `nexus/verifiers/domain/concurrency/buggy_targets_batch_b01.py` | 34 |
| `nexus/verifiers/domain/concurrency/concurrency_core.py` | 45 |
| `nexus/verifiers/domain/concurrency/fixed_targets.py` | 78 |
| `nexus/verifiers/domain/concurrency/fixed_targets_batch_b01.py` | 57 |
| `nexus/verifiers/packs/astropy_pack.py` | 23 |
| `nexus/verifiers/packs/django_pack.py` | 22 |
| `nexus/benchmarks/replay_dashboard.py` | 70 |
| `nexus/evaluation/challenge_harness.py` | 38 |
| `nexus/engine/verifiers/base.py` | 12 |
| `nexus/engine/verifiers/refactor_guard.py` | 41 |
| `nexus/oracle/promote.py` | 32 |
| `nexus/gate/__init__.py` | 0 |
| `nexus/gate/experimental_gate.py` | 168 |
| `nexus/gate/gate_judge.py` | 46 |
| `nexus/guardrails/__init__.py` | 0 |
| `nexus/guardrails/runtime_guardrails.py` | 17 |

`.gitignore`: the whitelist lines `!nexus/benchmarks/` and `!nexus/benchmarks/replay_dashboard.py`
are removed. `nexus/benchmarks/` held only that file.
`ARCHIVED_2026-10-12.md`: the `nexus/oracle/promote.py` row now points here.

## Kept

- **The m1 `concurrency_bug_02` benchmark fixture group.**
  `scripts/bench/m1_real_local_solve_benchmark.py` (task `concurrency_bug_02`) and
  `tests/benchmark/test_local_model_executor_planner_path.py` open these files by path, and
  `tests/nightly_quarantine_items/tests_unit_verifiers_concurrency_test_race.py` names the test
  file. The group is untouched:
  - `nexus/verifiers/domain/concurrency/buggy_targets_batch_b02.py`;
  - `fixed_targets_batch_b02.py`, which `test_concurrency_batch_b02.py` imports;
  - `nexus/verifiers/domain/common_core/state_guards.py`, which both of the above import;
  - the `__init__.py` files of `nexus/verifiers/domain`, `common_core/` and `concurrency/`;
  - the tests `tests/unit/verifiers/concurrency/{test_race,test_concurrency_batch_b02}.py`.

  Moving this group or retiring `concurrency_bug_02` is a separate REWIRE-OR-DELETE decision.
- **`nexus/verifiers/packs/{registry,base,__init__}.py`.** `nexus/committee/controller.py`
  imports `PackRegistry` at module level. The controller is on the live executor path. Removing
  these files needs a controller change first.
- **`nexus/verifiers/registry.py` and `contracts.py`.** The controller uses them.
- **`nexus/evaluation/manifest_manager.py`.** `ci_gate`, `baseline_gate` and `drift_stop_gate`
  use it.
- **Not in this batch:** `nexus/core/ash_template_resolver.py` (KEEP: the forecast_gate path
  uses it) and `nexus/engine/extension_guard.py` (it must go with the legacy-engine
  `autonomic_router` chain).

## Tests

Deleted. These 19 files import only batch-C modules: 834 lines, 48 test ids.
- `tests/gates/test_experimental_gate.py` (176)
- `tests/unit/gate/{__init__,test_gate_judge,test_gate_judge_purity}.py` (0, 21, 26)
- `tests/unit/guardrails/test_runtime_guardrails.py` (6)
- `tests/unit/verifiers/astropy/{__init__,test_astrophysics_guard,test_astropy_extended,test_astropy_io_roundtrip}.py`
  (0, 39, 39, 5)
- `tests/unit/verifiers/concurrency/{test_concurrency_batch_b01,test_concurrency_green,test_concurrency_stress,test_deadlock}.py`
  (74, 69, 79, 38)
- `tests/unit/verifiers/django/{test_core_extended,test_core_logic,test_migration_guard,test_migration_order}.py`
  (34, 55, 59, 53)
- `tests/unit/verifiers/{test_domain_prototypes,test_refactor_guard}.py` (19, 42)

Edited. These files also cover live code. Every test id is kept.
- `tests/integration/test_capability_existence_155.py`: `nexus.gate.gate_judge`,
  `nexus.gate.experimental_gate`, `nexus.engine.verifiers.refactor_guard` and the three
  `nexus.verifiers.domain` guards join `RETIRED_MODULES`.
- `tests/services/test_archived_capabilities_2026_10_12.py`: drops the file exclusion for the
  deleted `nexus/oracle/promote.py`. `nexus.oracle.promote` stays in the no-import scan.
- `tests/integration/test_v28_contract_sealing.py`:
  `test_memory_volatility_does_not_affect_gate_verdict` now asserts that `nexus.gate` is gone.
  The other two cases are unchanged.
- `tests/unit/singularity/test_v28_smoke_and_regression.py`: `test_shortest_main_path_smoke`
  keeps its state, replay, telemetry and evidence steps. Its gate step now asserts that
  `nexus.gate` is gone.
- `tests/unit/verifiers/common_core/test_core_contracts.py`: `test_locks` asserts that
  `lock_helpers` is gone. `test_dcl` (the kept `state_guards`) is unchanged.
- Four files used a deleted pack or verifier only as a fixture for live code. A test-local stub
  now stands in for it, with the same name-sanity rule:
  - `tests/research/test_candidate_evidence_committee_integration.py` (committee candidate
    evidence collection);
  - `tests/unit/committee/test_data_flow_v267.py` (committee feedback, retry and abstention);
  - `tests/unit/calibration/test_tuner_and_packs.py` (`PackRegistry` activation);
  - `tests/unit/verifiers/test_plugin_flow.py` (`VerifierRegistry` to controller).

  These cases cover the live `CommitteeControllerV263`, `PackRegistry` and `VerifierRegistry`.
  They pass on base and on head with the same outcomes.

Added: `tests/services/test_archived_phase2_batch_c_2026_10_21.py` (62 ids). For each retired
module it checks four things:
- the module is absent as a file, a package directory or a same-named data file;
- `find_spec` cannot find it;
- no `.py` under `nexus/` or `scripts/` imports it (`scripts/archive/` excluded). The scan uses
  the AST and resolves relative imports and `import_module`/`__import__`/`find_spec` literals;
- no text file there names it by dotted or slash path.

It also pins that the kept fixture group and `packs/{registry,base}` still import. A
non-vacuity test checks that each import and naming form is flagged and that `nexus.gateway`
and `buggy_targets_batch_b02` are not.
