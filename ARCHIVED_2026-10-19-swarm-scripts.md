# ARCHIVED 2026-10-19 (dead v18–v23 swarm scripts)

Retirement of the dead swarm subsystem scripts and the last executable parts of the
already-archived `nexus/federation/fleet_manager.py`, plus removal of the silent fake-route
fallback in `nexus/services/self_heal_selector.py`. Tracking issue: #2637 (source: the
2026-10-18 modernization assessment, security table and technical-debt list). The credentials
those scripts referred to were revoked by the Owner on 2026-10-18.

Variant used: **unreachable + manifest, no physical deletion**, as in `ARCHIVED_2026-10-12.md`
(#1863), `ARCHIVED_2026-10-13.md` (#1922) and `ARCHIVED_2026-10-13-legacy-engine.md` (#2070).
`.nexus-core/config.toml` has `deletion_policy = "FORBID"`. Script bodies are left byte-identical
except for one inserted ARCHIVED block right after the import section. That block emits a
`DeprecationWarning` on import and raises `SystemExit` when the file is run as a script, so the
hard-coded default tokens and the name-matching kills (`nexus_cli.py --swarm-mode`) in
these files can no longer execute. Physical deletion is deferred to a follow-up deletion PR.

Why dead: every script drives `./swarm-manager` or `nexus_cli.py --swarm-mode` inside a
`nexus-swarm/` directory. That directory no longer exists, and the Go swarm it built was retired
(`ARCHIVED_2026-10-16-rust-go.md`). The kills match by name, which breaks the kill-by-PID-only rule.

## Manifest

| # | Path | Evidence (git grep on origin/main 7815707cb, code files, excluding docs/archive/wiki/egg-info) | State | Deletion PR |
| --- | --- | --- | --- | --- |
| 1 | `scripts/node_fleet_mgr_v22.py` | only importers: `scripts/execute_scaling_audit_v22.py:7`, `scripts/v23_scale_audit.py:7` (both retired here); has a name-matching kill (line 51) and a default token | refuses to run, warns on import | pending |
| 2 | `scripts/stress_test_swarm_v18.py` | no importer, no workflow/Taskfile/plist reference | refuses to run, warns on import | pending |
| 3 | `scripts/test_multi_region_swarm_v19.py` | no importer; not collected by pytest (lives under `scripts/`); default token, name-matching kill | refuses to run, warns on import | pending |
| 4 | `scripts/test_swarm_v20_otel.py` | no importer; default token, name-matching kill | refuses to run, warns on import | pending |
| 5 | `scripts/test_swarm_v21_nsp.py` | no importer; default token, name-matching kill | refuses to run, warns on import | pending |
| 6 | `scripts/v23_scale_audit.py` | no importer; runs `./swarm-manager` in `nexus-swarm/`; default token | refuses to run, warns on import | pending |
| 7 | `scripts/execute_scaling_audit_v22.py` | no importer (only `muse_nexus.egg-info/SOURCES.txt`, a build artifact); default token | refuses to run, warns on import | pending |
| 8 | `scripts/stress_test_nsp_v22.py` | only importers: `scripts/execute_scaling_audit_v22.py:8`, `scripts/v23_scale_audit.py:8` (both retired here); default token | refuses to run, warns on import | pending |
| 9 | `scripts/tests/p3_swarm_stress.py` | no importer; runs `nexus-swarm/swarm-manager` | refuses to run, warns on import | pending |
| 10 | `nexus/federation/fleet_manager.py` | already archived and warning on import since #1863 (`ARCHIVED_2026-10-12.md` row 3); no non-test importer (only `tests/federation/test_fleet_manager.py`, `tests/test_lab_only_deprecations.py`, `tests/services/test_archived_capabilities_2026_10_12.py`) | `stop_fleet()` now raises instead of the name-matching kill (old line 42); the CLI (default token) raises `SystemExit`; `get_node_id`/`start_fleet` kept for the existing tests | pending |
| 11 | `nexus/federation/{__init__,config,node_launcher,node_registry}.py` | unchanged, as recorded in `ARCHIVED_2026-10-12.md` row 3; only test importers | left byte-identical | pending |

## Self-heal selector fix (not a retirement)

`nexus/services/self_heal_selector.py` imported `nexus.core.learning.compute_route_weights`,
a module that does not exist (`nexus/core/learning/` is absent on origin/main). The `except
Exception` then returned a hard-coded `rust-v16` candidate, so every Repair phase
(`nexus/engine/phases/repair.py:104`, its only production caller) recorded a fake
swarm-gated route. The loader now returns no candidates and logs a warning, and
`select_self_heal_route` fails closed with reason `self_heal_candidate_source_missing`. The
Repair phase already handles `fail-closed` by running the same `try_local_repair` that the old
swarm stub (`_swarm_repair`) proxied to, so repair behaviour is unchanged apart from the
truthful route record.

## Tests

- `tests/ops/test_retired_swarm_scripts_2637.py` (new): every retired script carries the marker,
  is listed here, and exits non-zero from an empty cwd without creating files; the fleet manager
  CLI refuses to run.
- `tests/federation/test_fleet_manager.py::test_stop_fleet`: same id; now asserts the refusal and
  that no subprocess runs.
- `tests/services/test_self_heal_selector.py`: two new cases (missing source fails closed, no
  hard-coded fallback); `test_self_heal_selector_uses_swarm_for_healthy` keeps its id and now
  injects a healthy candidate.
