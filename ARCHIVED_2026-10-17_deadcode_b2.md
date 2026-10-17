# ARCHIVED 2026-10-17 (dead-code batch B2)

Physical deletion of 67 proven-unused `nexus/services/local_heal` modules: the 66 modules of the
p3-p8 dry-run / shadow / rollout / smoke series listed as batch B2 in the dead-code proof, plus
`degradation_policy.py`, which was moved here from B3 (#2496) because only B2 modules
(`p6_receipt`, `p6_runtime_hook`, and B3's `degradation_controller`, already deleted) imported it.
Tracking issue: #2514 (kept open for the live-witness pilot, #2453). Decision: Owner (James),
2026-10-17, chat 「B2–B4 做」: delete batches B4, B3 and B2 of the dead-code proof, one PR per
batch (B4: #2489, B3: #2496). Originals are preserved on branch `archive/2026-10-17-deadcode-b2-pre`
(= `origin/main` 9a8b60cfec3e22be7fb76a9c8e276a3aa23fd9e2, pushed before this change).

Evidence: `~/Workspace/nexus-handoffs/2026-10-13-online-ab/DEADCODE_PROOF_20261016.md` (§2 batch
B2, §5 method, §6 appendix; scripts in `deadcode_proof_scripts/`). The proof ran at 219fa4ca7; it
was re-run on 9a8b60cfe before deleting: `dc_an.py` / `dot.py` (AST import graph incl.
function-level and relative imports, string and `import_module`/`__import__`/`_try_import_class`
literals, dotted/slash path text, bare-name search), the §5 `rg` commands, bare-import and
`sys.path` greps, and the launchd plists on both Macs. Every importer of these 67 modules is another
module of the batch or a test; no module of the batch is reachable from the Gateway roots,
`nexus_cli` or `scripts/ops`. Every remaining `local_heal` module still imports after the deletion.

Untouched as required: `p3_local_retry_stub.py` / `p3_local_retry_stub_runtime.py` (named by
`scripts/ops/self_hosted_task_service_dependency_map.py`; neither imports a B2 module),
`telemetry.py`, `env_resolver.py`, `preflight.py`, `anchored_edit.py`, the UNCERTAIN and
SCRATCH-ONLY modules. `docs/plans/self_hosted_task_service_dependency_map.json` still lists
`four_stage_orchestrator` / `p3_shadow_orchestrator` as importers of the retry stubs; its guard
(`tests/architecture/test_self_hosted_task_service_dependency_map.py`) reports drift as a GAP skip,
and the JSON is left for its owner to regenerate.

## Modules (67, 7,979 lines)

| path | lines |
|---|---:|
| `nexus/services/local_heal/four_stage_orchestrator.py` | 112 |
| `nexus/services/local_heal/local_model_apply_dry_run.py` | 75 |
| `nexus/services/local_heal/local_solve_dry_run_loop.py` | 95 |
| `nexus/services/local_heal/memory_action_receipt.py` | 54 |
| `nexus/services/local_heal/p3_authority_coupling.py` | 91 |
| `nexus/services/local_heal/p3_closeout_decision.py` | 220 |
| `nexus/services/local_heal/p3_cloud_candidate_stub.py` | 120 |
| `nexus/services/local_heal/p3_dry_run_invariants.py` | 114 |
| `nexus/services/local_heal/p3_dry_run_schema.py` | 140 |
| `nexus/services/local_heal/p3_local_cheap_verifier.py` | 93 |
| `nexus/services/local_heal/p3_local_cheap_verifier_runtime.py` | 157 |
| `nexus/services/local_heal/p3_local_diagnosis_runtime.py` | 222 |
| `nexus/services/local_heal/p3_p6_advisory_consumer.py` | 136 |
| `nexus/services/local_heal/p3_provider_readiness.py` | 118 |
| `nexus/services/local_heal/p3_shadow_invariants.py` | 157 |
| `nexus/services/local_heal/p3_shadow_orchestrator.py` | 189 |
| `nexus/services/local_heal/p3_shadow_promotion_policy.py` | 181 |
| `nexus/services/local_heal/p3_shadow_receipt.py` | 142 |
| `nexus/services/local_heal/p3_synthetic_e2e_trace.py` | 174 |
| `nexus/services/local_heal/p3_synthetic_provider.py` | 198 |
| `nexus/services/local_heal/p3_synthetic_provider_adapter.py` | 176 |
| `nexus/services/local_heal/p3_synthetic_provider_receipt.py` | 96 |
| `nexus/services/local_heal/p5_memory_bridge.py` | 54 |
| `nexus/services/local_heal/p5_p6_memory_context.py` | 132 |
| `nexus/services/local_heal/p5_selection_memory.py` | 65 |
| `nexus/services/local_heal/p6_closeout_decision.py` | 139 |
| `nexus/services/local_heal/p6_heldout_dry_run_harness.py` | 79 |
| `nexus/services/local_heal/p6_heldout_e2e_trace.py` | 100 |
| `nexus/services/local_heal/p6_heldout_monitor_adapter.py` | 59 |
| `nexus/services/local_heal/p6_heldout_planner.py` | 62 |
| `nexus/services/local_heal/p6_heldout_readiness.py` | 94 |
| `nexus/services/local_heal/p6_heldout_validator.py` | 194 |
| `nexus/services/local_heal/p6_mainline_boundary.py` | 27 |
| `nexus/services/local_heal/p6_p3_handoff_contract.py` | 37 |
| `nexus/services/local_heal/p6_p3_handoff_trace.py` | 83 |
| `nexus/services/local_heal/p6_receipt.py` | 88 |
| `nexus/services/local_heal/p6_rollout_canary.py` | 85 |
| `nexus/services/local_heal/p6_rollout_monitor.py` | 116 |
| `nexus/services/local_heal/p6_rollout_policy.py` | 59 |
| `nexus/services/local_heal/p6_rollout_receipt.py` | 83 |
| `nexus/services/local_heal/p6_runtime_hook.py` | 84 |
| `nexus/services/local_heal/p7_armor_evidence_manifest.py` | 66 |
| `nexus/services/local_heal/p7_armor_invariants.py` | 123 |
| `nexus/services/local_heal/p7_armor_readiness.py` | 129 |
| `nexus/services/local_heal/p7_armor_receipt.py` | 96 |
| `nexus/services/local_heal/p7_armor_synthetic_trace.py` | 147 |
| `nexus/services/local_heal/p8_c_authority_auditor.py` | 60 |
| `nexus/services/local_heal/p8_c_call_budget_auditor.py` | 57 |
| `nexus/services/local_heal/p8_c_p9_readiness.py` | 76 |
| `nexus/services/local_heal/p8_c_receipt_auditor.py` | 103 |
| `nexus/services/local_heal/p8_c_redaction_auditor.py` | 64 |
| `nexus/services/local_heal/p8_c_smoke_evidence_manifest.py` | 74 |
| `nexus/services/local_heal/p8_e_final_preflight.py` | 163 |
| `nexus/services/local_heal/p8_e_post_smoke_validator.py` | 208 |
| `nexus/services/local_heal/p8_human_approval_intake.py` | 207 |
| `nexus/services/local_heal/p8_network_smoke_approval.py` | 92 |
| `nexus/services/local_heal/p8_network_smoke_boundary.py` | 150 |
| `nexus/services/local_heal/p8_network_smoke_executor.py` | 51 |
| `nexus/services/local_heal/p8_network_smoke_receipt.py` | 61 |
| `nexus/services/local_heal/p8_one_call_lock.py` | 102 |
| `nexus/services/local_heal/p8_one_smoke_preflight.py` | 138 |
| `nexus/services/local_heal/p8_one_smoke_runner.py` | 593 |
| `nexus/services/local_heal/p8_post_smoke_validator.py` | 180 |
| `nexus/services/local_heal/p8_redaction_guard.py` | 46 |
| `nexus/services/local_heal/p8_smoke_prompt_capsule.py` | 95 |
| `nexus/services/local_heal/p8_smoke_result_validator.py` | 75 |
| `nexus/services/local_heal/degradation_policy.py` | 123 |

## Tests

Deleted (63 files, 9729 lines): every test function in them exercises a deleted module,
or (one case in each of six `tests/effects/test_p3_*` files) re-reads an evidence artifact those modules
produced. The artifacts under `artifacts/` are left as history.
`tests/effects/test_p3_authority_coupled_trace_artifact.py` (127),
`tests/effects/test_p3_executor_dry_run_evidence_matrix_strict.py` (226),
`tests/effects/test_p3_executor_dry_run_evidence_matrix.py` (202),
`tests/effects/test_p3_shadow_evidence_matrix.py` (220),
`tests/effects/test_p3_synthetic_e2e_trace_artifact.py` (192),
`tests/effects/test_p3_synthetic_provider_evidence_matrix.py` (256),
`tests/effects/test_p6_guarded_runtime_ab.py` (298),
`tests/effects/test_p8_one_network_smoke_receipt_v2.py` (244),
`tests/effects/test_p8_one_smoke_receipt_v1.py` (217),
`tests/integration/test_local_model_universal_solve_dry_run_seam.py` (105),
`tests/services/local_heal/test_four_stage_orchestrator.py` (270),
`tests/services/local_heal/test_p3_cheap_verifier_runtime.py` (101),
`tests/services/local_heal/test_p3_local_diagnosis_runtime.py` (185),
`tests/unit/local_heal/test_local_model_apply_dry_run.py` (47),
`tests/unit/local_heal/test_local_model_executor_p3_cloud_stub.py` (34),
`tests/unit/local_heal/test_local_solve_dry_run_loop.py` (90),
`tests/unit/local_heal/test_p3_authority_coupling.py` (149),
`tests/unit/local_heal/test_p3_closeout_decision.py` (443),
`tests/unit/local_heal/test_p3_dry_run_invariants.py` (220),
`tests/unit/local_heal/test_p3_dry_run_schema.py` (268),
`tests/unit/local_heal/test_p3_p6_advisory_consumer.py` (172),
`tests/unit/local_heal/test_p3_provider_readiness.py` (171),
`tests/unit/local_heal/test_p3_shadow_invariants.py` (216),
`tests/unit/local_heal/test_p3_shadow_promotion_policy.py` (133),
`tests/unit/local_heal/test_p3_shadow_receipt.py` (190),
`tests/unit/local_heal/test_p3_synthetic_e2e_trace.py` (287),
`tests/unit/local_heal/test_p3_synthetic_provider_adapter.py` (245),
`tests/unit/local_heal/test_p3_synthetic_provider_receipt.py` (214),
`tests/unit/local_heal/test_p3_synthetic_provider.py` (285),
`tests/unit/local_heal/test_p5_memory_action_receipt.py` (109),
`tests/unit/local_heal/test_p5_memory_bridge.py` (75),
`tests/unit/local_heal/test_p5_p6_memory_context.py` (52),
`tests/unit/local_heal/test_p6_closeout_decision.py` (230),
`tests/unit/local_heal/test_p6_degradation_policy.py` (145),
`tests/unit/local_heal/test_p6_heldout_dry_run_harness.py` (76),
`tests/unit/local_heal/test_p6_heldout_e2e_trace.py` (35),
`tests/unit/local_heal/test_p6_heldout_planner_readiness.py` (54),
`tests/unit/local_heal/test_p6_heldout_planner.py` (54),
`tests/unit/local_heal/test_p6_heldout_validator.py` (191),
`tests/unit/local_heal/test_p6_mainline_boundary.py` (48),
`tests/unit/local_heal/test_p6_p3_handoff_contract.py` (56),
`tests/unit/local_heal/test_p6_p3_handoff_trace.py` (34),
`tests/unit/local_heal/test_p6_receipt.py` (93),
`tests/unit/local_heal/test_p6_rollout_canary.py` (128),
`tests/unit/local_heal/test_p6_rollout_monitor.py` (108),
`tests/unit/local_heal/test_p6_rollout_policy.py` (88),
`tests/unit/local_heal/test_p6_rollout_receipt.py` (106),
`tests/unit/local_heal/test_p6_runtime_hook.py` (108),
`tests/unit/local_heal/test_p7_armor_evidence_manifest.py` (64),
`tests/unit/local_heal/test_p7_armor_invariants.py` (126),
`tests/unit/local_heal/test_p7_armor_readiness.py` (81),
`tests/unit/local_heal/test_p7_armor_receipt.py` (52),
`tests/unit/local_heal/test_p7_armor_synthetic_trace.py` (60),
`tests/unit/local_heal/test_p8_c_independent_audit.py` (131),
`tests/unit/local_heal/test_p8_e_final_preflight.py` (126),
`tests/unit/local_heal/test_p8_e_post_smoke_validator.py` (189),
`tests/unit/local_heal/test_p8_human_approval_intake.py` (326),
`tests/unit/local_heal/test_p8_network_smoke_boundary.py` (175),
`tests/unit/local_heal/test_p8_network_smoke.py` (127),
`tests/unit/local_heal/test_p8_one_call_lock.py` (115),
`tests/unit/local_heal/test_p8_one_smoke_preflight.py` (150),
`tests/unit/local_heal/test_p8_post_smoke_validator.py` (321),
`tests/unit/local_heal/test_p8_smoke_prompt_capsule.py` (89).

Edited (every test id kept; test functions that exercised a deleted module now assert
`importlib.util.find_spec(<module>) is None`; tests of live code unchanged):
- `tests/unit/local_heal/test_p3_local_retry_stub.py` (1 of 12; the retry-stub cases are unchanged),
- `tests/unit/local_heal/test_p3_shadow_orchestrator.py` (17 of 18),
- `tests/unit/local_heal/test_memory_lesson_content_injection.py` (1 of 9),
- `tests/unit/local_heal/test_local_model_executor_p3_dry_run_hook_strict.py` (2 of 19; the
  `LocalModelExecutor` dry-run hook cases are unchanged),
- `tests/integration/test_model_json_routing_2174.py` (3 of 9),
- `tests/unit/local_heal/test_p3_cloud_candidate_stub.py` (11 of 12; `p3_local_diagnosis` case kept),
- `tests/unit/local_heal/test_p3_local_cheap_verifier.py` (10 of 11; `output_understanding` case kept),
- `tests/unit/local_heal/test_p5_selection_memory.py` (4 of 5; `fuzzy_functions` case kept),
- `tests/integration/test_capability_existence_155.py`: `p3_provider_readiness` and `p5_memory_bridge`
  join `RETIRED_MODULES`.
Imports that became unused were removed and import blocks re-sorted (ruff F401/I001).

Compared with the proof: `test_memory_lesson_content_injection.py`,
`test_local_model_executor_p3_dry_run_hook_strict.py`, `test_p3_cloud_candidate_stub.py`,
`test_p3_local_cheap_verifier.py` and `test_p5_selection_memory.py` were listed as
delete-with-batch but also test live code, so they were edited instead;
`test_p6_receipt.py` (listed as edit) and `test_p6_degradation_policy.py` (from B3) only exercise
deleted modules now that `degradation_policy` is in this batch, so they were deleted;
`test_model_json_routing_2174.py` (not in the proof) imports two B2 modules and was edited.

## Guard

`tests/services/test_archived_deadcode_b2_2026_10_17.py`: each name is absent as a module, a
package directory or a same-named `.json`/`.txt` file; each dotted module is not importable; no `.py`
file under `nexus/` or `scripts/` (except `scripts/archive/`) imports one (AST, relative imports and
`import_module`/`__import__`/`find_spec` literals resolved); no text file there names one by dotted or
slash path; plus a non-vacuity test (the kept `p3_local_retry_stub*`, `p3_local_diagnosis` and
`anchored_edit` are not flagged).

Historical mentions left as is: `ARCHIVED_2026-10-1*.md`, `docs/reports/`, `docs/plans/`,
`artifacts/`, `scripts/archive/`, `nexus_wiki_vault/`.
