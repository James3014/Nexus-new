# ARCHIVED 2026-10-21 (Phase-2 dead-code batch B)

Physical deletion of the Phase-2 batch B items judged DELETE-SAFE in Issue #2584: two unused
Codex/Antigravity launcher scripts and their guard helper, two legacy personal scripts (Telegram
PTY bridge, script dashboard and its page), the self-hosted MCP competition/campaign tools with
their two backing modules, and the lab-only Planner Auditor. Decision: Owner (James) standing
approval for Phase-2 lightweight deletion, 2026-10-20 (DELETE-SAFE items only, one batch per PR,
independent review and green required checks), and 「好，開始做 #2584 刪除」 on 2026-10-21.
Base: `origin/main` 32f9e1907; every deleted file is recoverable from that commit.

Evidence: the #2584 per-symbol evidence for batch B (gathered read-only at 01dc1015 on
2026-10-20), re-verified on 32f9e1907 before deleting:
- `git grep` (non-test, non-docs, non-archive) for every module path (dotted and slash), class
  and function name, and tool name: the only remaining non-test hits were inside the batch
  (`refactor_campaign` -> `worker_competition`; `self_hosted_mcp` -> both; `morning_briefing.py`
  -> `script_dashboard.py` -> `Swarm_Dashboard.html`; `start_antigravity_nexus_enforced.sh` ->
  `start_codex_nexus_enforced.sh` -> `codex_run_guard.py`) and two docstrings
  (`agy_write_admission.py`, `codex_run_boundary.py`), updated here. No `importlib` /
  `import_module` / `__import__` literal names a batch item; `pyproject.toml` `[project.scripts]`
  has none.
- The 10 sibling repos (`git grep` on HEAD: nexus-core, nexus-runtime, devspace, nexus-learning,
  nexus-open-swe-runtime, nexus-opencli-reviewer, repository-intelligence-engine, repo-learning,
  nexus-workbench, nexus-deployment-lab) and a fresh read-only clone of cairnwork (add5ee1): no hit.
- This Mac (M4): `~/Library/LaunchAgents`, `~/.local/bin`, shell rc files and crontab: the only hit
  is `com.musecore.tgbridge.plist.bak`, a not-loaded backup whose `ProgramArguments` run a different
  copy, `~/Downloads/obsidian/知識庫/01_Operations/scripts/tg_pty_bridge.py`, not this repo.
  The evidence reports the Mac mini clean.
- Live Gateway: importing `nexus.orchestrator.unified_mcp_gateway` does not load
  `self_hosted_mcp`, `self_hosted_mcp_http`, `refactor_campaign`, `worker_competition` or
  `planner_auditor` (re-checked in the worktree venv; the evidence ran it against the deployed
  venv). `nexus.executors.codex_run_boundary` is loaded and is kept.
- `codex_run_guard.py` (item 1c) condition holds: its only callers were
  `start_codex_nexus_enforced.sh` (deleted together) and tests; `CodexCliExecutor` imports
  `nexus.executors.codex_run_boundary`, not the guard. Its `git-config-fingerprint` subcommand
  only wrapped `agy_write_admission.git_config_fingerprint`, which stays.

## Deleted files (10, 2,406 lines)

| path | lines |
|---|---:|
| `scripts/ops/start_codex_nexus_enforced.sh` | 276 |
| `scripts/ops/start_antigravity_nexus_enforced.sh` | 9 |
| `scripts/ops/codex_run_guard.py` | 186 |
| `scripts/tg_pty_bridge.py` | 167 |
| `scripts/script_dashboard.py` | 711 |
| `scripts/morning_briefing.py` | 11 |
| `scripts/Swarm_Dashboard.html` | 406 |
| `nexus/orchestrator/refactor_campaign.py` | 192 |
| `nexus/orchestrator/worker_competition.py` | 384 |
| `nexus/core/planner_auditor.py` | 64 |

## Edited production code

- `nexus/orchestrator/self_hosted_mcp.py` (-144 lines): the 8 competition/campaign tools
  (`nexus_self_hosted_compete_task`, `_get_competition`, `_integrate_competition`,
  `_create_refactor_campaign`, `_advance_refactor_campaign`, `_get_refactor_campaign`,
  `_rollback_refactor_campaign`, `_push_competition`) are removed from the tool list and from
  `_call_tool`, with the `self.competition` / `self.campaigns` coordinators and their imports.
  Everything else in the file is unchanged (the remaining SelfHostedTaskService tools are KEEP);
  calling a removed tool now returns the existing `unknown tool` error.
- Docstrings only: `nexus/executors/agy_write_admission.py` (`git_config_fingerprint`) and
  `nexus/executors/codex_run_boundary.py` (module docstring) no longer name the deleted scripts.

## Tests

Deleted (every case exercises only deleted code; 3 files, 485 lines, 18 test ids):
`tests/security/test_legacy_script_hardening_2620.py` (98, 8; only the bridge and dashboard),
`tests/nexus/orchestrator/test_refactor_campaign.py` (66, 2),
`tests/nexus/orchestrator/test_worker_competition.py` (321, 8).
None of them sits under a directory that an impact-map row on the base selects, so the exact-base
impact gate never collects them on the base side.

Kept with every id, cases rewritten to assert absence (their directories, `tests/ops` and
`tests/core`, are selected whole by base impact-map rows, so an id must not vanish there):
- `tests/ops/test_start_codex_nexus_enforced.py` (22 ids) and
  `tests/ops/test_codex_run_guard_sweep.py` (6 ids): each case asserts the launcher, proxy and
  guard files are gone and `find_spec("scripts.ops.codex_run_guard") is None`.
- `tests/core/test_layer_ports.py`: `nexus/core/planner_auditor.py` stays an explicit parameter
  (`RETIRED_CORE_FILES`) of `test_core_modules_do_not_load_upper_layer_modules`, and that case
  asserts the file is absent; all other ids unchanged.
- `tests/governance/test_planner_depth.py` (3 ids): the two `HealthScorer.apply_snapshot`
  plan-density cases cover live code and are unchanged apart from the dropped auditor call; the
  auditor-only case asserts `find_spec("nexus.core.planner_auditor") is None`.

Edited (every test id is kept):
- `muse_nexus.egg-info/SOURCES.txt` (tracked): the rows for the three deleted `scripts/*.py`
  files are removed (`tests/ops/test_source_inventory_integrity.py`).
- `tests/ops/test_codex_run_boundary.py` (30 ids): the boundary module is live
  (`CodexCliExecutor`), so cases that checked a boundary behaviour through the launcher now call
  `nexus.executors.codex_run_boundary` directly with the same planted mutations: 13 target-integrity
  cases (escaping symlinks, `.git` pointer, nested / case-variant / unreadable `.git`, committed
  baseline) on a detached worktree, 4 auth write-back cases, the disposable-HOME case (planted
  `~/.ssh`, `~/.config/gh`, `~/.gitconfig` and Codex history/config/sessions are not copied) and
  the env-allowlist case. The 7 launcher-only cases (process-group kill, guard exit codes, state
  dir, HOME removal, rejected-run write-back) assert the launcher and guard are gone; HOME removal
  after a run and rejected-run write-back stay covered for the live path by
  `tests/nexus/executors/test_codex_run_boundary_executor.py`.
- `tests/nexus/orchestrator/test_state_id_path_traversal.py` (all ids kept): the
  `worker_competition` / `refactor_campaign` cases assert `importlib.util.find_spec(...) is None`;
  the two MCP cases assert the retired tools are rejected as unknown and touch no state.
- `tests/nexus/orchestrator/test_self_hosted_mcp.py`: the tool-surface case asserts the 8 tools are
  gone (all other tool and schema assertions unchanged); the compete-task zero-dispatch case now
  checks every retired tool is an unknown-tool error with zero service calls.
- `tests/architecture/test_effect_owner_uniqueness.py`: `COMPETITION_CALLER`
  (`WorkerCompetitionCoordinator.integrate_winner`) leaves `DECLARED`/`EDGES` and is labelled
  `RETIRED`; `ControlledIntegrationManager.integrate_task_state` now has no admitted caller, so any
  new caller fails the scan. The compatibility-domain case asserts the retirement.
- `tests/integration/test_capability_existence_155.py`: `nexus.core.planner_auditor` joins
  `RETIRED_MODULES`.
- `tests/services/test_archived_capabilities_2026_10_13.py`: `planner_auditor` moves from
  `ARCHIVED_MODULES` to `DELETED_MODULES`.
- `tests/test_lab_only_deprecations.py`: `planner_auditor` joins `DELETED` (asserts absence).

## Kept (out of scope or not DELETE-SAFE)

- `nexus/orchestrator/self_hosted_mcp.py` rest, `nexus/orchestrator/self_hosted_mcp_http.py` and
  `scripts/ops/nexus_self_hosted_mcp_http.py` (#2584 items 4b/4c: whole-file removal is
  REWIRE-OR-DELETE).
- CLI `nexus delivery-gate` (5a, KEEP) and the Forecast Gate (5b, NEEDS-MORE).
- `nexus/executors/codex_run_boundary.py` (live via `CodexCliExecutor`) and
  `agy_write_admission.git_config_fingerprint` (now without a production caller; left for a
  separate decision).
- `nexus/orchestrator/governed_push.py` (`GovernedPushManager`) and
  `ControlledIntegrationManager.integrate_task_state`: their only production caller was
  `worker_competition.py`. Both are named in security/architecture inventories
  (`owner_representation_transport_inventory.py`, the effect-owner test), so they are left for a
  separate decision rather than deleted here.
- `scripts/ops/start_gemini_nexus_enforced.sh` (not in the batch).

## Guard

`tests/services/test_archived_phase2_batch_b_2026_10_21.py`: each deleted file is absent (also as
a package directory or same-named `.py`/`.json`/`.txt`); each module is not importable
(`importlib.util.find_spec`); no `.py` file under `nexus/` or `scripts/` (except `scripts/archive/`)
imports one (AST, relative imports and `import_module`/`__import__`/`find_spec` literals resolved);
no text file there names a deleted path, module or tool; the self-hosted MCP server no longer serves
the 8 tools; plus a non-vacuity test.

Historical mentions left as is: `ARCHIVED_2026-10-12.md`, `ARCHIVED_2026-10-13.md`,
`ARCHIVED_2026-10-17_deadcode_b4.md`, `docs/`, `tasks/`, `scripts/archive/`, `nexus_wiki_vault/`
(including `06_Ops/NEXUS_ENFORCED_LAUNCH.md`, which still documents the launcher; it is left
unchanged so the generated Wiki artifacts stay reproducible, and needs a Wiki regeneration
follow-up).
