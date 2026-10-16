# ARCHIVED 2026-10-16 (retired Go swarm; Rust kept for now)

Tracking issue: #2334. Decision: Owner (James), in chat on 2026-10-16. The decision covers
physical deletion of the retired Rust/Go code listed in the repo-rewrite assessment
(knowledge `nexus/architecture/2026-10-16-repo-rewrite-assessment.md` §3.2, §6 item 1,
§9). It follows the #2197 route: physical deletion with the `owner-approved-deletion`
label. Originals are kept on branch `archive/2026-10-16-rust-go-retired`, cut from
`origin/main` f573a24ee before this change.

The `.nexus-core/config.toml` `deletion_policy = "FORBID"` setting makes the advisory Core
check go red on any deletion. Per that file's own comment, the real gate is the required
Deletion guard plus the `owner-approved-deletion` label.

## Physically deleted

| Path | Files | Lines | Why it is safe to delete |
| --- | ---: | ---: | --- |
| `nexus_swarm/` | 66 | 5,510 | It has no launchd job, workflow, Taskfile target, `pyproject` package or `python -m` caller on either Mac, and no live tree imports it. The only importers are listed in the next rows, plus three archived CLI modules (#1906) that import it inside function bodies only. |
| `nexus-swarm-v22-prod/` | 26 | 1,553 | It was marked `# ARCHIVED` in #1763/#1784. Nothing builds it. |
| `scripts/test_local_swarm.sh` | 1 | 9 | A RETIRED stub that only pointed at `nexus_swarm/manager`. |
| `scripts/ops/wisdom_daemon.py` | 1 | 39 | Imports `nexus_swarm` at module level. Nothing calls it. |
| `scripts/ops/v23_1_guard_backtest.py` | 1 | 58 | Same as above. |
| `scripts/ops/v23_1_hardened_backtest.py` | 1 | 90 | Same as above. |
| `scripts/ops/v23_1_healing_precision_check.py` | 1 | 66 | Same as above. |
| **Total** | **97** | **7,325** | |

`tests/ops/test_swarm_deploy_path.py` keeps its six test ids, because the exact-base impact gate reads a vanished parameterized id as an ambiguous change (IMPACT_UNKNOWN); each test now asserts the retired state. `tests/ops/test_retired_go_swarm_removed.py` keeps the deletion deliberate. It checks that
no source is left in either tree and that the `nexus_swarm` modules cannot be imported. It
also checks that no module in `nexus/` or `scripts/` imports `nexus_swarm`, and that the
archived CLI commands fail closed.

## Kept (live references; follow-up)

- **`nexus-core-rs/`, `nexus/bridge/rust_kernel.py`, `nexus/bridge/cutover_manager.py`,
  `tests/integration/test_rust_wave3_cutover.py`.** Policy manifest
  (`docs/reports/policy-manifest.v2.json`) hard-lane policies **P-GATE-03**
  (`nexus-core-rs/src/receipt_verifier.rs`) and **P-FLOW-01**
  (`nexus-core-rs/src/flow_machine.rs` plus `tests/integration/test_rust_wave3_cutover.py`)
  are `enforcement_mode: block`. Deleting these files turns
  `tests/ops/test_policy_manifest_schema.py::test_real_manifest_hard_lane_policies_are_behaviourally_tested[modify|promote|cutover]`
  red with `SOURCE_FILE_NOT_FOUND`; this was reproduced locally. Retiring or rebinding those
  two policies is a governance change and needs its own Owner decision. That is the same
  reason #2197 kept `nexus-core-rs/`.
- **`.github/workflows/policy-lane-gate.yml`** L12, L24 and L97 watch `nexus-core-rs/src`.
  This is a workflow change, so it needs separate Owner approval and owner credentials.
  It is moot while the crate is kept.
- **`generate_full_matrix_report.py` and `generate_rollback_drill_report.py`** (the
  `RUST_BINARY` path) and **`nexus/engine/governance_bridge.py`** (the binary lookup, which
  falls back to "Binary not found") go together with the crate.
- **`Taskfile.yml`**: its cargo/go targets build `packages/core` and `packages/swarm`, not
  `nexus-core-rs/` or `nexus_swarm/`, so they are not part of this surface.
- **`nexus/cli/commands/{guard,healing,swarm}.py`**: these are archived and never
  registered (#1906). `tests/services/test_archived_capabilities_2026_10_13.py` imports
  them, and their `nexus_swarm` imports are function-local. They stay as they are.
