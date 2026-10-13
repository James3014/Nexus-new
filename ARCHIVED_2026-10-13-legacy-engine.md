# ARCHIVED 2026-10-13 (legacy-engine batch)

Retirement of the legacy `NexusEngine` (`nexus/engine/coordinator.py`) and everything that only
existed to build or drive it. Tracking issue: #2047. Decision: owner, 2026-10-13 ("舊 engine 可退"),
under the standing rule "retire only what a test proves unused or unreachable from the production
path; archive (unreachable + manifest + archive branch), no physical deletion". Originals are
preserved on branch `archive/2026-10-13-legacy-engine` (cut from `origin/main` 582822e10 before
this change). Evidence bundle: `~/Workspace/nexus-handoffs/2026-10-13-legacy-engine/REPORT.md`
(key `LE` below; `LE/usage`, `LE/execution`, `LE/scripts`).

Variant used: **unreachable + manifest, no physical deletion**, same as `ARCHIVED_2026-10-12.md`
and `ARCHIVED_2026-10-13.md` (`.nexus-core/config.toml` `deletion_policy = "FORBID"`). Every import,
registration, port binding, CLI binding and workflow trigger below was removed; each archived
module emits `DeprecationWarning("ARCHIVED 2026-10-13 legacy-engine: ...")` on import. The warning
is appended at the end of each module (no line shifts, no new imports), so it fires once the module
has finished importing. Physical deletion waits for the deletion PR.

## Why the engine can go

- **Not on the production path.** `nexus run` -> `execute_canonical_product_task`
  (`nexus/engine/canonical_task_seam.py`) -> CapabilityPlanner -> mainchain has no NexusEngine or
  CommandService fallback (its docstring says so and `tests/engine/test_canonical_task_seam.py`
  checks it). The MCP gateway (`unified_mcp_gateway.py`) and the self-hosted task service import
  only `execute_canonical_product_task` / `build_canonical_dispatch_envelope` from the seam; the
  external-intelligence service only `build_canonical_planner_admission`; the DSH workflow guard
  (`~/.local/bin/nexus-dsh-workflow`) does not import Nexus code at all. A static import-closure
  walk (lazy in-function imports counted, `LE/scripts/reach.py`) from the production roots (the
  `nexus` console script with every registered command, MCP gateway + its HTTP entry, self-hosted
  task service and worker, external-intelligence automation, the planner executor registry, the
  wiring audit, `ci_gate.py`, every Python entry of every other workflow) reached NexusEngine only
  through the seam's legacy builders (`build_engine`, `build_command_service`,
  `build_legacy_cli_service`, `execute_single_task_via_service`). With those cut, none of the
  modules below is reachable (`LE/usage/reach_before.txt`, `reach_after.txt`). The one port-based
  edge (`autonomic_router.AutonomicRouter`, used by the planner executor) is handled in row 6.
- **What the remaining callers were.** `NexusCLI` compatibility shim (only caller:
  `scripts/ops/task_runner.py::run_phase_task`, a manual runner that already returns rc=1 on any
  exception), CLI `nexus nexus swarm run`, `nexus.engine.cli_runner_async` (no importer),
  `nexus.evaluation.eval_harness` (no importer), `nexus.services.cli_commands_service` (only the
  never-registered, already archived `nexus/cli/commands/*`), and `scripts/ci/run_smoke_benchmark.py`
  in the `Nexus Smoke Benchmark` workflow.
- **What it does today (executed on a fixture checkout of main 582822e10, `LE/execution`).**
  `nexus nexus swarm run "fix typo in README heading"` and `... "add function answer() returning 42
  to hello.py"`: both route the repair to `rust-v16` (the archived `nexus-rust-v16` gitlink),
  `tokens_used=0`, `Final Health: 35.0% | Success: False`, envelope `FAILED / runtime_defect`, rc=1;
  side effects: a line appended to tracked `Daily_Log.md`, `.nexus/incidents/*.json`,
  `events_sourced.jsonl`, twelve `.nexus/*` directories, `reminders.json`. No patch, no model call.
- **The nightly smoke benchmark was a constant.** `NexusEngine.run_benchmark` returns
  `[{"health": 100.0, "status": "PASS", ...}]` without reading the cases. Locally, the real
  three-case manifest and a manifest naming one nonexistent case both report `pass_rate 1.0`
  (`LE/execution/smoke_local*.log`). CI: 1014 runs since 2026-08-09, last 1000 = 976 success /
  24 failure (`LE/usage/nexus_smoke_recent_runs.json`); the uploaded report is the same constant
  (`LE/usage/smoke_artifact/`). Nothing consumes the artifact: no workflow, script or repo
  (Nexus-new, nexus-core, nexus-automation-repos, devspace) references `nexus-benchmark-report`,
  `NEXUS_BENCHMARK_REPORT` or the workflow; it is not a required status check (main's ruleset
  requires only "Full published Git history secret audit" and "Deletion guard").
- **Usage.** No Nexus-new `.nexus/incidents`, swarm reports or receipts from this path. The legacy
  repo `~/Workspace/nexus` has five incident packs (2026-07-07 .. 2026-08-09), all `FAILED`
  (four are "fix phantom success"). Last functional change to `coordinator.py`: 2026-06-13
  (`219c70326`). One GitHub issue mentions NexusEngine (#1733, closed).

## Manifest

| # | Path | Evidence | State | Deletion PR |
| --- | --- | --- | --- | --- |
| 1 | `nexus/engine/coordinator.py` (`NexusEngine`) | only importers: the seam's legacy builders (now fail closed), `nexus/containers.py` (row 11), root script `verify_v9_hardening.py` (not collected, not run); runs fail every task (`LE/execution`) | warns on import | pending |
| 2 | `nexus/engine/bootstrap.py`, `pipeline.py` (P-X-D-R-A-C), `pipeline_stages.py`, `pipeline_repair.py`, `recursive_repair_loop.py`, `repair_setup_service.py` (federation hooks already removed 2026-10-12), `autonomic_routing_service.py` | each imported only by the module above it in this chain (`coordinator` -> `bootstrap`/`pipeline`/`repair_setup_service`/`autonomic_routing_service`; `pipeline` -> `pipeline_stages`/`pipeline_repair` -> `recursive_repair_loop`). `pipeline_repair` is listed in `tests/services/test_formal_mainchain_callers.py` because it *calls* `run_mainchain`; nothing on the production path calls it | warn on import | pending |
| 3 | `nexus/engine/cli_runner_async.py` | no importer | warns; `execute_tactical_node` now raises `LegacyEngineArchivedError` | pending |
| 4 | `nexus/app/command_service.py` (`NexusCommandService`) | wrapper of NexusEngine; importers: the seam (string import, removed), `eval_harness` (row 5), lab-only `nexus/benchmark/benchmark_runner.py` (row 10) | warns on import | pending |
| 5 | `nexus/evaluation/eval_harness.py` (`EvalHarness`) | no importer; drove NexusEngine through CommandService and derived `model_time_sec = pipeline_time * 0.27` | warns on import | pending |
| 6 | `nexus/engine/autonomic_router.py` + planner node `autonomic_router` | node: no `policy_evaluator.py` enable rule (forced only), `consumer_effect=NONE`, `reason_code=route_probe_not_production_execute` (wiring audit row, `capability_coverage_gap.py`: `reserved_until_planner_ssot_migration`); module importers: `autonomic_routing_service` (row 2), port `autonomic_router.AutonomicRouter`, `nexus/learning/router_nas_tuner.py` (only via `reflex_loop` <- `bootstrap`), `scripts/ops/router_policy_benchmark.py` and `scripts/scratch/phase13_*` (manual) | port binding removed from `nexus/engine/core_ports.py`; `_exec_autonomic_router` returns the archived receipt; reason `archived_legacy_engine_autonomic_router_2026-10-13` in `ARCHIVED_CAPABILITY_REASONS` / `SKIP_REASONS`; wiring audit reports the row RETIRING; module warns | pending (module) |
| 7 | `nexus/engine/canonical_task_seam.py` legacy builders `build_engine`, `build_command_service`, `build_legacy_cli_service`, `execute_single_task_via_service`; class `LegacyTaskServiceAdapter` | only path from any registered entry to NexusEngine | builders raise `LegacyEngineArchivedError` (`reason = archived_legacy_engine_2026-10-13`); adapter class and `importlib` import removed; `execute_canonical_product_task` untouched | n/a (code removed) |
| 8 | `scripts/engine/nexus_cli.py` `NexusCLI` shim; CLI `nexus nexus swarm run` (`scripts/engine/commands/swarm.py`) | shim: only caller `scripts/ops/task_runner.py` (manual); `swarm run`: executed above, fails every task | shim raises `LegacyEngineArchivedError`; `swarm` module no longer registered (the group's other command, `quiet-moment`, was archived in #1906), module warns | pending (`swarm.py`) |
| 9 | `nexus/services/cli_commands_service.py` | only caller `nexus/cli/utils.py::_get_service`, used only by the archived `nexus/cli/commands/*` (#1906) | warns; construction raises via `build_legacy_cli_service` | pending |
| 10 | `nexus/benchmark/benchmark_runner.py` | lab-only since #1740, no importer; builds NexusEngine through `nexus.containers` and CommandService | warning text now `ARCHIVED 2026-10-13 legacy-engine` (keeps `#1740`) | pending |
| 11 | `nexus/containers.py` (`NexusContainer`) | cannot be imported at all: `dependency_injector` is not a declared dependency (not in `pyproject.toml` or `uv.lock`); only importer row 10 | left byte-identical (it can never run, so a warning would never fire) | pending |
| 12 | `scripts/ci/run_smoke_benchmark.py` + workflow `.github/workflows/nexus-smoke.yml` (companion change) | constant PASS, unconsumed artifact (above); the workflow is not a Core-protected path | script exits 1 with the archive notice and warns on import; workflow keeps its name but only has `workflow_dispatch`, and its single step prints the notice and fails; `openwiki/workflows/github-actions.md` row updated | pending (both) |

Not archived (named production importer or not legacy-engine code):

| Path | Verdict | Why |
| --- | --- | --- |
| `nexus/governance/capability_gate.py` | KEEP | `nexus/services/prompt_builder.py` imports it; reached from the `nexus` CLI through `nexus/services/gateway.py` (BattlesuitGateway, e.g. `content:rewrite`) |
| `nexus/core/capability_gate.py` facade | already archived (#1906, `ARCHIVED_2026-10-13.md` row 10) | unchanged |
| `nexus/engine/benchmark_runner.py` (`bench effort`) | KEEP (CLI) | registered command `bench effort`; does not import NexusEngine |
| `scripts/nexus_pilot_cli.py`, `nexus/pilot_cli/*` | out of scope (not legacy engine) | an HTTP/subprocess client of the gateway; imports no engine module. Its health actions call `nexus:check` / `nexus:self-heal`, which are not registered commands (pre-existing; not changed here) |
| `.github/workflows/benchmark-ci.yml` | out of scope (not legacy engine) | runs `scripts/ci/run_swebench_subset.py`, which shells out to a `nexus_benchmark.sh` that does not exist; 65 of 65 listed runs failed. Separate retirement decision |

## Tests

- Historical node ids are kept. Rewritten to assert the retired behavior:
  `tests/engine/test_canonical_task_seam.py` (5 builder tests), `tests/engine/test_cli_runner_async.py`
  (2), `tests/engine/test_cli_local_assist_advisor_gate2.py::test_execute_single_task_propagates_execution_context`,
  `tests/test_cli_output_contract.py::test_nexus_cli_compat_shim_uses_canonical_service_factory`,
  `tests/test_service_decomposition.py::test_cli_facade_redirection`,
  `tests/integration/test_n27_five_preexisting_to_100_percent.py` (autonomic_router now fail-closed),
  `tests/ops/test_capability_wiring_audit.py` (autonomic_router RETIRING).
- 40 test files that exercise archived modules keep running unchanged and carry an end-of-file
  `ARCHIVED 2026-10-13 legacy-engine` note naming the modules; the deletion PR removes them with
  the modules.
- New: `tests/services/test_archived_legacy_engine_2026_10_13.py` (archived receipt and skip for
  `autonomic_router`, port unbound, seam builders fail closed, every archived module warns,
  production entries load none of them, no live importer, `swarm run` gone, `NexusCLI` fails
  closed, smoke script refuses and no workflow runs it).

## Left for the deletion PR or a later decision

- Modules reachable only through the legacy engine but outside this batch's scope (they keep
  working, no warning): `LE/usage/orphaned_by_cut.txt` lists every file the cut makes unreachable
  by static imports (153, including this batch's files). Port-bound ones stay reachable through
  `nexus/engine/core_ports.py` (`phases/research`, `phases/audit`, `forecast_gate_service`,
  `self_healing_selector`, ...). Notable pure leftovers: `nexus/engine/reflex_loop.py`,
  `nexus/learning/router_nas_tuner.py`, `nexus/engine/repair_loop_service.py`,
  `repair_attempt_service.py`, `pipeline_research.py`, `pipeline_crystal.py`, `pipeline_outcome.py`,
  `phase_executors.py`, `phase_factory.py`.
- `verify_v9_hardening.py` (repo root, not collected, not run) imports `NexusEngine`.
- Planner-side metadata that still names `autonomic_router` (`PLANNER_EXECUTION_CONTRACTS`
  control entry, `capability_coverage_gap.py`, receipt adapters / receipt policy lists, runtime
  node table). The runtime maturity flip rides the next nexus-runtime PR, as for the #1906 nodes.
- `gh workflow disable nexus-smoke.yml` after merge is optional (the workflow has no automatic
  trigger left).
