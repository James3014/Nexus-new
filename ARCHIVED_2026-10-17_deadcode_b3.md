# ARCHIVED 2026-10-17 (dead-code batch B3)

Physical deletion of 35 proven-unused `nexus/services/local_heal` modules (the non-p-series part of
the local_heal package). Tracking issue: #2491. Decision: Owner (James), 2026-10-17, chat
「B2–B4 做」: delete batches B4, B3 and B2 of the dead-code proof, one PR per batch (B4: #2489,
`ARCHIVED_2026-10-17_deadcode_b4.md`). Originals are preserved on branch
`archive/2026-10-17-deadcode-b3-pre` (= `origin/main` 5d0186632e4050335acfffb2950eae4d14b94120,
pushed before this change). Impact-map anchor rows: #2493.

Evidence: `~/Workspace/nexus-handoffs/2026-10-13-online-ab/DEADCODE_PROOF_20261016.md` (§2 batch
B3, §5 method, §6 appendix; scripts in `deadcode_proof_scripts/`). The proof ran at 219fa4ca7; it
was re-run on 5d0186632 before deleting: `dc_an.py` / `dot.py` (AST import graph incl.
function-level and relative imports, string and `import_module`/`__import__`/`_try_import_class`
literals, dotted/slash path text, bare-name search), the §5 `rg` commands, bare-import and
`sys.path` greps, references to the deleted test files from scripts/workflows/docs, and the launchd
plists on both Macs. The only importers of these modules are inside the batch
(`runbook_compliance_cli` -> `runbook_compliance`) or tests. Every remaining `local_heal` module
still imports after the deletion.

## Kept from the proof's B3 list (2 modules)

- `local_heal/anchored_edit.py`: live non-test reader. `scripts/bench/rebuild_ax_substrate.py`
  names it as the fixture of the `anchored_edit_gap_00{1..4}` substrate tasks, and
  `scripts/bench/run_anchored_edit_gap_00{1..4}_regression.py` run
  `tests/unit/local_heal/test_anchored_edit.py` cases against it.
- `local_heal/degradation_policy.py`: imported by `local_heal/p6_receipt.py` and
  `local_heal/p6_runtime_hook.py`, which are B2 modules and still exist; it moves to the B2 batch.

Untouched as required: `local_heal/telemetry.py`, `env_resolver.py`, `preflight.py`,
`p3_local_retry_stub*.py`, the UNCERTAIN and SCRATCH-ONLY modules.

## Modules (35, 3,928 lines)

| path | lines |
|---|---:|
| `nexus/services/local_heal/abbreviated_traceback.py` | 140 |
| `nexus/services/local_heal/assertion_extractor.py` | 73 |
| `nexus/services/local_heal/ast_locator.py` | 108 |
| `nexus/services/local_heal/candidate_generation.py` | 403 |
| `nexus/services/local_heal/concurrency.py` | 26 |
| `nexus/services/local_heal/degradation_controller.py` | 34 |
| `nexus/services/local_heal/effect_ledger.py` | 76 |
| `nexus/services/local_heal/evaluator.py` | 29 |
| `nexus/services/local_heal/evidence_freeze.py` | 109 |
| `nexus/services/local_heal/export_guard.py` | 165 |
| `nexus/services/local_heal/function_localizer.py` | 96 |
| `nexus/services/local_heal/fuzzy_spec_registry.py` | 105 |
| `nexus/services/local_heal/heterogeneous_candidate_provider.py` | 85 |
| `nexus/services/local_heal/hunk_localizer.py` | 102 |
| `nexus/services/local_heal/judge_selector.py` | 65 |
| `nexus/services/local_heal/linear_replay_runner.py` | 208 |
| `nexus/services/local_heal/local_model_capability_executor_registry.py` | 112 |
| `nexus/services/local_heal/local_qwen_evidence_gate.py` | 131 |
| `nexus/services/local_heal/memory_belief_signal.py` | 38 |
| `nexus/services/local_heal/micromerger.py` | 43 |
| `nexus/services/local_heal/parser.py` | 126 |
| `nexus/services/local_heal/patch_intent.py` | 125 |
| `nexus/services/local_heal/pre_patch.py` | 121 |
| `nexus/services/local_heal/protocol_transition_receipt.py` | 67 |
| `nexus/services/local_heal/quota_monitor.py` | 42 |
| `nexus/services/local_heal/repro_preflight.py` | 108 |
| `nexus/services/local_heal/runbook_compliance.py` | 347 |
| `nexus/services/local_heal/runbook_compliance_cli.py` | 65 |
| `nexus/services/local_heal/sandbox.py` | 57 |
| `nexus/services/local_heal/shadow_receipt.py` | 165 |
| `nexus/services/local_heal/source_hash_guard.py` | 123 |
| `nexus/services/local_heal/strategy_conditioned_packer.py` | 96 |
| `nexus/services/local_heal/strategy_differentiator.py` | 122 |
| `nexus/services/local_heal/swarm_committee_bridge.py` | 126 |
| `nexus/services/local_heal/verifier_replay_gate.py` | 90 |

## Tests

Deleted (30 files, 2749 lines): every test function in them exercises a deleted module.
`tests/benchmark/test_heterogeneous_local_model_armor.py` (105),
`tests/effects/test_ea_shadow_runtime_attachment.py` (199),
`tests/services/local_heal/test_degradation_controller.py` (130),
`tests/services/local_heal/test_quota_monitor.py` (55),
`tests/unit/local_heal/test_assertion_extractor.py` (48),
`tests/unit/local_heal/test_candidate_generation.py` (340),
`tests/unit/local_heal/test_effect_ledger.py` (119),
`tests/unit/local_heal/test_evidence_freeze.py` (89),
`tests/unit/local_heal/test_fuzzy_spec_registry.py` (100),
`tests/unit/local_heal/test_heterogeneous_candidate_provider.py` (77),
`tests/unit/local_heal/test_judge_selector.py` (45),
`tests/unit/local_heal/test_local_model_capability_executor_registry.py` (84),
`tests/unit/local_heal/test_local_qwen_evidence_gate.py` (109),
`tests/unit/local_heal/test_strategy_differentiator.py` (132),
`tests/unit/local_heal/test_swarm_committee_bridge.py` (101),
`tests/unit/test_abbreviated_traceback.py` (78),
`tests/unit/test_ast_locator.py` (95),
`tests/unit/test_ast_micromerger_tdd.py` (29),
`tests/unit/test_deepswe_concurrency_tdd.py` (25),
`tests/unit/test_function_localizer.py` (47),
`tests/unit/test_hunk_localizer.py` (25),
`tests/unit/test_parser_deep_clean.py` (83),
`tests/unit/test_patch_intent.py` (85),
`tests/unit/test_prepatch_invocation_boundary.py` (43),
`tests/unit/test_prepatch_preparation_slice.py` (47),
`tests/unit/test_protocol_transition_receipt.py` (57),
`tests/unit/test_shadow_receipt.py` (105),
`tests/unit/test_source_hash_guard.py` (106),
`tests/unit/test_strategy_conditioned_packer.py` (111),
`tests/unit/test_verifier_replay_gate.py` (80).

Edited (every test id kept; test functions that exercised a deleted module now assert
`importlib.util.find_spec(<module>) is None`; tests of live code unchanged):
- `tests/benchmark/test_h7_capability_receipt_denial_fields.py` (7 of 12 cases; the claim-boundary,
  capability-receipt and denial-contract cases are unchanged),
- `tests/services/local_heal/test_fuzzy_spec_registry_paw.py` (7 of 11; the `fuzzy_functions`
  cases are unchanged),
- `tests/unit/local_heal/test_anchored_edit.py` (3 `runbook_compliance` cases of 20; the
  `AnchoredEdit` / protocol cases the bench scripts run are unchanged),
- `tests/unit/local_heal/test_env_taxonomy_and_preflight.py` (4 `repro_preflight` cases of 17),
- `tests/unit/local_heal/test_runbook_compliance.py` (15 of 16; the `evaluation_gate` regression
  binding case is unchanged),
- `tests/unit/test_export_guard.py` (15 of 22; the `S2TExportGuard` cases are unchanged),
- `tests/unit/test_local_heal_decoupled.py` (2 `parser` cases of 4),
- `tests/unit/test_swe_integration.py` (6 `parser` cases of 8),
- `tests/unit/local_heal/test_candidate_search.py` (1 of 3),
- `tests/effects/test_p5_branch_replay_memory_arms.py`, `tests/unit/local_heal/test_g_track.py`:
  drop an unused import of a deleted module,
- `tests/integration/test_capability_existence_155.py`: 6 B3 modules join `RETIRED_MODULES`,
- `tests/services/test_archived_capabilities_2026_10_13.py`: `linear_replay_runner` moves from
  `ARCHIVED_MODULES` to `DELETED_MODULES` (must not be importable; still in the no-import scan).
Imports that became unused were removed and import blocks re-sorted (ruff F401/I001).

Pre-existing broken test, left as is: `tests/unit/test_local_resolver.py` imports the deleted
`local_heal.sandbox` and `local_heal.evaluator` inside two test functions, but the file already
fails to import on base (`from nexus.services.local_heal.localizer import Localizer`: no such name)
and is `--ignore`d by `pytest.ini`, so it is never collected. It is unchanged here (out of scope).

The proof listed `test_h7_capability_receipt_denial_fields.py`, `test_p5_branch_replay_memory_arms.py`,
`test_fuzzy_spec_registry_paw.py`, `test_anchored_edit.py`, `test_env_taxonomy_and_preflight.py`,
`test_p6_degradation_policy.py`, `test_runbook_compliance.py`, `test_export_guard.py`,
`test_local_heal_decoupled.py` and `test_swe_integration.py` as delete-with-batch; they also test
live code (or a kept module), so they were edited instead (`test_p6_degradation_policy.py` and
`test_p6_receipt.py` need no change because `degradation_policy` stays).

## Guard

`tests/services/test_archived_deadcode_b3_2026_10_17.py`: each name is absent as a module, a
package directory or a same-named `.json`/`.txt` file; each dotted module is not importable; no `.py`
file under `nexus/` or `scripts/` (except `scripts/archive/`) imports one (AST, relative imports and
`import_module`/`__import__`/`find_spec` literals resolved); no text file there names one by dotted or
slash path; plus a non-vacuity test (kept `anchored_edit` / `degradation_policy` are not flagged).

Historical mentions left as is: `ARCHIVED_2026-10-1*.md`, `docs/reports/`, `docs/plans/`,
`scripts/archive/`, `nexus_wiki_vault/`.
