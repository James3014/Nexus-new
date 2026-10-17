# ARCHIVED 2026-10-17 (dead-code batch B4)

Physical deletion of 23 proven-unused top-level `nexus/services` modules (wiki-era helpers,
retired executors, misc). Tracking issue: #2475. Decision: Owner (James), 2026-10-17, chat
「B2–B4 做」: delete batches B4, B3 and B2 of the dead-code proof, one PR per batch, as B1+B5 in
#2349 (`ARCHIVED_2026-10-16_deadcode_b1_b5.md`). Originals are preserved on branch
`archive/2026-10-17-deadcode-b4-pre` (= `origin/main` fdd8657eb2b6d11362bc2515a650d2bf57b6d405,
pushed before this change).

Evidence: `~/Workspace/nexus-handoffs/2026-10-13-online-ab/DEADCODE_PROOF_20261016.md` (§2 batch
B4, §5 method, §6 appendix; scripts in `deadcode_proof_scripts/`). The proof ran at 219fa4ca7; it
was re-run on fdd8657eb before deleting: `dc_an.py` / `dot.py` (AST import graph incl.
function-level and relative imports, string and `import_module`/`__import__`/`_try_import_class`
literals, dotted/slash path text, bare-name search), the §5 `rg` commands, and the launchd plists
on both Macs. All 23 are still **PROVEN-UNUSED**: no non-test importer; the only importers are
inside the batch (`construction_service` -> `predictive_audit`; `normalization_engine` names
`planner_enhancer.py` as a path string). Bare-word hits outside the batch are unrelated names:
the `aos_oracle` capability key in `nexus/core/capability_registry.py` and
`scripts/ops/capability_wiring_audit.py` (archived executor key, served by `aos_service`, not this
module), `dual_phase_d` as a tool label in `nexus/core/nono_compressor.py`, `steward` in
`nexus/core/steward.py` (`MemorySteward`, a different module) and `scripts/script_dashboard.py`
(category keyword), `rbac` inside a SWE-bench patch fixture, `mock_llm` as a local variable name in
tests. Kept: none.

## Modules (23, 1,730 lines)

| path | lines |
|---|---:|
| `nexus/services/ambiguity_guard.py` | 85 |
| `nexus/services/aos_oracle.py` | 47 |
| `nexus/services/arweave_writer.py` | 64 |
| `nexus/services/construction_service.py` | 80 |
| `nexus/services/context_crystal.py` | 34 |
| `nexus/services/dual_phase_d.py` | 44 |
| `nexus/services/feature_tasker.py` | 40 |
| `nexus/services/fp_bridge_v2.py` | 25 |
| `nexus/services/fs_watcher.py` | 70 |
| `nexus/services/governance_sink.py` | 50 |
| `nexus/services/local_deliberation_lane.py` | 287 |
| `nexus/services/mcp_delegator.py` | 333 |
| `nexus/services/mock_llm.py` | 31 |
| `nexus/services/normalization_engine.py` | 69 |
| `nexus/services/planner_enhancer.py` | 81 |
| `nexus/services/predictive_audit.py` | 111 |
| `nexus/services/rbac.py` | 30 |
| `nexus/services/s2t_repair.py` | 53 |
| `nexus/services/shannon_audit.py` | 35 |
| `nexus/services/shogun_optimizer.py` | 26 |
| `nexus/services/steward.py` | 67 |
| `nexus/services/swarm_graph.py` | 34 |
| `nexus/services/ui_budget.py` | 34 |

## Tests

Deleted (they import only B4 modules; 5 files, 373 lines):
`tests/integration/test_s2t_repair_loop.py` (45),
`tests/services/test_mcp_delegator.py` (158),
`tests/services/test_planner_enhancer.py` (70),
`tests/test_watcher_eviction.py` (35),
`tests/unit/test_local_deliberation_lane.py` (65).

Edited (they also cover live code; every test id is kept, the B4 cases now assert absence):
- `tests/integration/test_capability_existence_155.py`: the 8 B4 modules join `RETIRED_MODULES`
  (their parametrized cases assert `ModuleNotFoundError`).
- `tests/integration/test_legacy_path_blocked.py`: drop the `NON_MODEL_JSON_PARSE_ALLOWLIST`
  entry for `nexus/services/mcp_delegator.py` (`MCPDelegator.delegate_mcp`); the test fails on
  stale entries.
- `tests/services/test_archived_capabilities_2026_10_12.py`: `aos_oracle` moves from
  `ARCHIVED_MODULES` to `DELETED_MODULES` (must not be importable; still in the no-import scan).
- `tests/test_lab_only_deprecations.py`: the `nexus.services.aos_oracle` case asserts the module
  is gone.
- `tests/test_governance_p6.py`: keeps the `PLoopManager` P6 settle transition, asserts
  `governance_sink` is gone.
- `tests/test_wisdom_synthesis.py`: the `WisdomSynthesizer` loop test is unchanged; the
  `predictive_audit` / `construction_service` cases assert absence.

The proof listed `test_archived_capabilities_2026_10_12.py`, `test_lab_only_deprecations.py`,
`test_governance_p6.py` and `test_wisdom_synthesis.py` as delete-with-batch; they also cover live
code (archived-capability receipts, lab-only warnings, `PLoopManager`, `WisdomSynthesizer`), so
they were edited instead.

## Guard

`tests/services/test_archived_deadcode_b4_2026_10_17.py`: each name is absent as a module, a
package directory or a same-named `.json`/`.txt` file; each dotted module is not importable
(`importlib.util.find_spec`); no `.py` file under `nexus/` or `scripts/` (except `scripts/archive/`)
imports one (AST, relative imports and `import_module`/`__import__`/`find_spec` literals resolved);
no text file there names one by dotted or slash path; plus a non-vacuity test.

Historical mentions left as is: `ARCHIVED_2026-10-12.md`, `ARCHIVED_2026-10-13.md`, `docs/reports/`,
`scripts/archive/`, `nexus_wiki_vault/`.
