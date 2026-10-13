# Capability wiring audit (2026-10)

Issue #1852 (batch 1 fixes: #1862; extension to all planner nodes: #1892). Original run base: origin/main 929a953d0; batch-1 matrix: origin/main 4dbac7875 plus #1862; current matrix: run 2026-10-12T22:57:52.380962+00:00 on origin/main aa095b305 plus #1892, pinned nexus-runtime 29a8dcf. Claim ceiling: `WIRING_AUDIT_EVIDENCE_ONLY` (no benchmark scored, no routing/admission change).

## Question

When the real planner -> registry -> executor path invokes a capability, does real code run and leave physical evidence, or is the result simulated or stubbed?

## Method

Script: `scripts/ops/capability_wiring_audit.py` (fixtures `scripts/ops/wiring_fixtures/<capability>/`, tests `tests/ops/test_capability_wiring_audit.py`). Raw matrix: `docs/experiments/capability_wiring_audit_2026-10.matrix.json` (the run also writes `artifacts/runtime/wiring_audit/<ts>/matrix.json`, per-capability receipts and workspaces; that tree is gitignored).

1. **Forcing.** `CapabilityPlanner` has no `required` constraint knob. The production planning seam (`plan_canonical_task_bundle`) only sees task text, `route_features`, pillars, codeintel and budget; `route.route_decision.selected_capabilities` is dropped there. The audit forces a node with the route-oracle line `Expected capability receipts: <node>` in the task statement, the same string the benchmark wearing contract uses. Every in-scope node except `llm_judge_panel` (out of scope) was selectable this way; none is NOT_SELECTABLE.
2. **Execution.** `run_mainchain` -> `UnifiedRuntime` -> registry invoker (`build_mainchain_capability_invokers`) -> `EXECUTOR_REGISTRY` executor, or the postflight invoker / Local stage. Every capability runs in a fresh copy of its fixture; cwd is the workspace because executors write `.nexus/...` relative to cwd. Executors are observed (not altered) through a recording wrapper that captures each `CapabilityReceipt`.
3. **Online channel.** A deterministic no-model stand-in declared as the admitted provider (Workforce route `fast_bounded_implementation`, controls from `canonical_task_seam._actual_runtime_controls` plus a declared `task_card`, the same shortcut as `scripts/ops/unified_runtime_scenarios.py`). Without a binding every capability is blocked at Workforce Admission before any invoker runs (`workforce_bindings must be an object mapping`). Claim/delivery gates therefore see `online_invoked=true` from the stand-in; their proof inputs (isolated verifier run, sha256 artifact, source-hash binding) are real.
4. **Assertions.** Each capability has a physical, input-dependent assertion (file on disk, hit, block, exit code) plus a negative control run through the same path. A capability whose outcome does not change between positive and negative input is STUB.
5. **Policy switches.** Production default sets neither `NEXUS_LOCAL_MODEL_CALL_ALLOWED` nor `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED` (grep: only tests, the A/B armor lane and canary helpers set them; `nexus run` does not). The audit runs production default first and only then the switch the blocked executor names: `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1` (same switch as the A/B armor lane; hyper, nightshift, swarm, multi_agent, committee and the Local stage), `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1` (autoreason, ddtree: the bodies are offline Python that make no provider call), `NEXUS_USE_COMMITTEE=1` (committee controller). I could not find where `nexus run` sets any of them, so these are not claimed to be what production sets; they are what each executor demands. Escalate-gated nodes (`ESCALATE_ONLY`) are also run untriggered (production default: `SKIPPED_POLICY_NOT_TRIGGERED`) and then with `route.escalate_triggered=True` (what `product_capability_canary_helper` sets).
6. **Model.** M5 tunnel `http://127.0.0.1:11434`, model `qwen2.5-coder:7b-instruct` (listed by `/api/tags`); nothing was started on this host.
7. **Coverage (#1892).** Every CapabilityPlanner node of the pinned runtime (57) now has a row: the 36 earlier rows plus 22 nodes the first audit skipped. Nodes whose execution contract has no physical callable (or whose executor can never run) get `NOT_EXECUTABLE:<reason>`; they are still forced, triggered and executed, and the observed result is kept in `observed_verdict`.
8. **Selection under production defaults.** For each new node the audit also plans *without* the forcing line, through the same seam (`plan_canonical_task_bundle`), with a task text / `route_features` that satisfies the node's `policy_evaluator.py` (or `capability_planner.py`) rule. `CanonicalTaskContext.planner_inputs()` forwards only `route_features`, so rules that read other `route` keys (`recommended_flow`, `msa_routing`, `prompt_compression`) are recorded as "rule input dropped by the seam". Column `selected without forcing` in the matrix.
9. **Role demanded by the forcing line.** The oracle line contains the node name; for `architecture_scout` and `integration_manager` that name contains a complex-task keyword (`architecture`, `integration`), so the planner demands Workforce role `main_engineering`. Those two scenarios bind the worker the policy resolves for `main_engineering` (still the no-model stand-in); everything else keeps `fast_bounded_implementation`.
10. **Online prompt observed.** The online stand-in writes the prompt it receives to `.wiring_audit_online_seen.json` in the workspace (observation only), which is how the prompt_compression row checks that the compressed context reached the online channel.
11. **Executor-only keys.** `EXECUTOR_REGISTRY` keys that no planner node, alias or execution contract maps to (computed, not listed by hand; `learning_closure` is excluded as RETIRING) are invoked directly with an empty plan under production default env in a scratch cwd. Verdict `UNREACHABLE_NO_PLANNER_NODE`; the matrix records gate, outcome, the quoted hard-coded lines (re-scanned from source each run) and any write under `/tmp/.nexus` or `/tmp/run`.

## Verdicts

- `REAL_UNATTESTED`: the executor ran, evidence refs exist and the artifact assertion passed, but the receipt still says `claim_boundary.simulated=true`. `REAL` is reserved for the same case with `simulated=false`, which never occurs.
- `SIMULATED`: executor runs but its inputs are hard-coded or fixture-provided. `STUB`: constant outcome, input-independent outcome, or gate passes without any checkable effect. `BLOCKED_<exact reason>`, `NOT_SELECTABLE`, `RETIRING`, `MODEL_UNAVAILABLE` as specified.
- `claim_boundary.simulated` is recorded in column `receipt_claims_simulated` and is **not** an execution signal: `CapabilityReceipt.to_dict()` emits `claim_boundary` without `simulated`, `ClaimBoundary` defaults it to true, and nothing in nexus-runtime or Nexus-new sets it false for capability receipts. All 29 executed rows said true at 929a953d0; since batch 1 the audit reads the Nexus-side attested receipt (see "Batch 1 fixes"), and runtime-produced receipts (postflight gates, prompt_compression) still say true.
- `NOT_EXECUTABLE:<reason>`: planner node with no runnable physical callable (`control_plane_reference`: contract `physical_callable=None` and no `EXECUTOR_REGISTRY` key; `no_live_connector`: the executor is an auth gate with nothing behind it).
- `UNREACHABLE_NO_PLANNER_NODE`: executor-registry key that no planner node can select.

## Result matrix (run 2026-10-12T22:57:52.380962+00:00, origin/main aa095b305 + #1892)

Verdict counts, all 58 rows (57 planner nodes + the `learning_closure` executor): `{"BLOCKED": 12, "NOT_EXECUTABLE": 4, "NOT_SELECTABLE": 1, "REAL": 24, "REAL_UNATTESTED": 4, "RETIRING": 6, "SIMULATED": 1, "STUB": 6}`.

- The 36 rows audited before: `{"BLOCKED": 9, "REAL": 17, "REAL_UNATTESTED": 3, "RETIRING": 6, "STUB": 1}`, identical to the post-batch-1 run (`{"BLOCKED": 9, "REAL": 17, "REAL_UNATTESTED": 3, "RETIRING": 6, "STUB": 1}`, run 2026-10-12T13:19:36 on origin/main 4dbac7875 + #1862). History: at 929a953d0 they were 14 REAL_UNATTESTED, 4 STUB, 3 SIMULATED, 9 BLOCKED, 6 RETIRING, 0 REAL.
- The 22 new rows: `{"BLOCKED": 3, "NOT_EXECUTABLE": 4, "NOT_SELECTABLE": 1, "REAL": 7, "REAL_UNATTESTED": 1, "SIMULATED": 1, "STUB": 5}`.

`research` is BLOCKED_EXTERNAL_AUTH at production default and REAL only with `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1`; `judge_panel`, `external_doc_scout` and `registry_sync` likewise record both attempts (see `policy_attempts` in the `.matrix.json`; the table shows the best verdict). federation, oracle_shadow, stress_test, ui_validator and benchmark are retired at planner level in the pinned runtime; learning_closure is an executor, not a planner node. Full strings are in the `.matrix.json`.

| capability | verdict | executor-level verdict (product path blocked) | production default, selected but untriggered | selected without forcing (production defaults) | executor (function @ file:line) | reached via | switches needed | receipt_claims_simulated |
|---|---|---|---|---|---|---|---|---|
| codeintel | REAL | - | - | - | _exec_codeintel @ nexus/core/capability_executor_registry.py:758 | EXECUTOR_REGISTRY | none | False |
| research | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_research @ nexus/core/capability_executor_registry.py:876 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| research_route | BLOCKED_execution_contract_violation:missing_outcome_field:control_plane_reference | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_research @ nexus/core/capability_executor_registry.py:876 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| hyper | BLOCKED_semantic_status=FAILED | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_hyper_sprint @ nexus/core/capability_executor_registry.py:1332 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | False |
| nightshift | BLOCKED_semantic_status=BLOCKED(terminal_status=FAILED):console:❌ [NightShift] Blocked by Phase Policy: PassRate=0.0%... | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_nightshift @ nexus/core/capability_executor_registry.py:1531 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| swarm | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1427 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| multi_agent | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1427 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| drone | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_drone @ nexus/core/capability_executor_registry.py:1472 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| ultra_review | BLOCKED_workforce_admission_blocked: demand_online: Requested role 'independent_review' is outside admitted roles for... | STUB | MISSING | - | _exec_ultra_review @ nexus/core/capability_executor_registry.py:1831 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| autoreason | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_autoreason @ nexus/core/capability_executor_registry.py:1239 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| ddtree | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_ddtree @ nexus/core/capability_executor_registry.py:2523 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| lancedb | REAL | - | - | - | _exec_lancedb @ nexus/core/capability_executor_registry.py:833 | EXECUTOR_REGISTRY | none | False |
| memory | REAL | - | - | - | _exec_memory @ nexus/core/capability_executor_registry.py:2092 | EXECUTOR_REGISTRY | none | False |
| mempalace_gate | REAL | - | - | - | _exec_mempalace @ nexus/core/capability_executor_registry.py:396 | EXECUTOR_REGISTRY | none | False |
| belief | REAL | - | - | - | _exec_belief @ nexus/core/capability_executor_registry.py:1142 | EXECUTOR_REGISTRY | none | False |
| artifact_gate | REAL_UNATTESTED | - | - | - | evaluate_postflight_gate @ nexus_runtime/support/services/online_nexus_context.py:858 | POSTFLIGHT_INVOKER | none | True |
| claim_gate | REAL_UNATTESTED | - | - | - | evaluate_postflight_gate @ nexus_runtime/support/services/online_nexus_context.py:858 | POSTFLIGHT_INVOKER | none | True |
| delivery_gate | REAL_UNATTESTED | - | - | - | evaluate_postflight_gate @ nexus_runtime/support/services/online_nexus_context.py:858 | POSTFLIGHT_INVOKER | none | True |
| acceptance_check | REAL | - | - | - | _exec_acceptance_check @ nexus/core/capability_executor_registry.py:2697 | EXECUTOR_REGISTRY | none | False |
| pregate | REAL | - | - | - | _exec_pregate @ nexus/core/capability_executor_registry.py:2287 | EXECUTOR_REGISTRY | none | False |
| forecast_gate | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_forecast_gate @ nexus/core/capability_executor_registry.py:3370 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| plan_quality_gate | REAL | - | - | - | _exec_plan_quality_gate @ nexus/core/capability_executor_registry.py:2150 | EXECUTOR_REGISTRY | none | False |
| sandbox | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_sandbox_runner @ nexus/core/capability_executor_registry.py:1540 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| harness_preflight_sensor | REAL | - | - | - | _exec_harness_preflight_sensor @ nexus/core/capability_executor_registry.py:2355 | EXECUTOR_REGISTRY | none | False |
| committee | BLOCKED_canonical_context_rejected: canonical_context_route_override_forbidden:codeintel.committee_proposals[].model | BLOCKED_semantic_status=FAILED | MISSING | - | _exec_committee @ nexus/core/capability_executor_registry.py:3180 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1,NEXUS_USE_COMMITTEE=1; route.escalate_trigge... | False |
| xray | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_xray @ nexus/core/capability_executor_registry.py:3591 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| metabolism | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_metabolism_resume @ nexus/core/capability_executor_registry.py:1896 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| meta_opt | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_meta_opt @ nexus/core/capability_executor_registry.py:3778 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| local_model_executor | BLOCKED_SELECTED_NOT_EXECUTED:planner_selected_no_runtime_executor:local_stage[local_output_not_delivered,candidate_n... | - | - | - | LocalModelExecutor.run @ nexus/services/local_heal/local_model_executor.py:1065 | LOCAL_STAGE | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 | True |
| repair_loop | BLOCKED_local_model_executor_not_proven,missing_candidate_hash,candidate_hash_not_applied,verifier_not_passed,local_r... | - | - | - | LocalModelExecutor.run @ nexus/services/local_heal/local_model_executor.py:1065 | LOCAL_STAGE | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 | True |
| semantic_failure_sensor | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; available_but_not_selected) | _exec_semantic_failure_sensor @ nexus/core/capability_executor_registry.py:2873 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| bdd_acceptance_skill | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; available_but_not_selected) | _exec_bdd_acceptance_skill @ nexus/core/capability_executor_registry.py:2919 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| jit_validation | SIMULATED | - | - | yes: jit_validation_signal | _exec_jit_validation @ nexus/core/capability_executor_registry.py:2805 | EXECUTOR_REGISTRY | none | False |
| semantic_searcher | REAL | - | - | yes: runtime_semantic_search_signal | _exec_semantic_searcher @ nexus/core/capability_executor_registry.py:2241 | EXECUTOR_REGISTRY | none | False |
| prompt_compression | REAL_UNATTESTED | - | - | no (optional; rule input dropped by seam: prompt_compression; available_but_not_selected) | build_prompt_compression_capability_invoker @ nexus_runtime/kernel/capabilities.py:408 | RUNTIME_INVOKER | none | True |
| asi_constraint_extractor | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: blocked_assumptions_require_cross_task_constraint_check | _exec_asi_constraint_extractor @ nexus/core/capability_executor_registry.py:3097 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| architecture_scout | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: architecture_scout_runtime_plan_required | _exec_architecture_scout @ nexus/core/capability_executor_registry.py:3056 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| formal_report | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: formal_or_public_report_requires_evidence_report | _exec_formal_report @ nexus/core/capability_executor_registry.py:3480 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| learn_mode | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: claim_or_citation_learning_signal | _exec_learn_mode @ nexus/core/capability_executor_registry.py:2589 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| learn_phase_slo | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: learn_phase_policy_needed | _exec_learn_phase_slo @ nexus/core/capability_executor_registry.py:2652 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| file_lock | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: multi_agent_write_boundary | _exec_file_lock @ nexus/core/capability_executor_registry.py:3292 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| direct_mode | NOT_EXECUTABLE:control_plane_reference | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; rule input dropped by seam: recommended_flow; available_but_not_selected) | - | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| msa_router | NOT_EXECUTABLE:control_plane_reference | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; rule input dropped by seam: msa_routing; available_but_not_selected) | - | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| research_control_plane | NOT_EXECUTABLE:control_plane_reference | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; research_control_or_experiment_signal,tier_l1_cost_control) | - | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| swarm_quiet_moment | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: swarm_write_boundary_required | _exec_swarm_quiet_moment @ nexus/core/capability_executor_registry.py:3651 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| integration_manager | BLOCKED_LEGACY_INTEGRATION_PATH_RETIRED_USE_CONTROLLED_INTEGRATION | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: integration_or_merge_signal | _exec_integration_manager @ nexus/core/capability_executor_registry.py:3560 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| autonomic_router | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; available_but_not_selected) | _exec_autonomic_router @ nexus/core/capability_executor_registry.py:636 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| judge_panel | BLOCKED_EXTERNAL_AUTH:no_judge_provider_configured | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: evidence_quality_judge_required_for_uncertain_or_multi_candidate_route | _exec_judge_panel @ nexus/core/capability_executor_registry.py:2952 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | True |
| llm_judge_panel | NOT_SELECTABLE | - | - | no (optional; available_but_not_selected) | _exec_llm_judge_panel @ nexus/core/capability_executor_registry.py:3029 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | None |
| external_doc_scout | NOT_EXECUTABLE:no_live_connector | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: claim_uncertainty_requires_external_fact_check | _exec_external_doc_scout @ nexus/core/capability_executor_registry.py:3941 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | True |
| learn_scheduler | BLOCKED_scheduler_exit_2 | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; available_but_not_selected) | _exec_learn_scheduler_service @ nexus/core/capability_executor_registry.py:1065 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| registry_sync | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: platform_registry_signal | _exec_registry_sync @ nexus/core/capability_executor_registry.py:3695 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| federation | RETIRING | - | - | - | - | - | none | None |
| oracle_shadow | RETIRING | - | - | - | - | - | none | None |
| stress_test | RETIRING | - | - | - | - | - | none | None |
| ui_validator | RETIRING | - | - | - | - | - | none | None |
| benchmark | RETIRING | - | - | - | - | - | none | None |
| learning_closure | RETIRING | - | - | - | - | - | none | None |

| capability | verdict reason | failed assertions / notes |
|---|---|---|
| codeintel | invoked_with_evidence_and_artifact_assertions_passed |  |
| research | invoked_with_evidence_and_artifact_assertions_passed |  |
| research_route | executor_or_runtime_blocked |  |
| hyper | executor_or_runtime_blocked | failed: sprint_status_success |
| nightshift | executor_or_runtime_blocked | failed: recovery_report_written, terminal_success |
| swarm | executor_or_runtime_blocked | failed: swarm_executed_workers, no_construct_only_rejection |
| multi_agent | executor_or_runtime_blocked | failed: swarm_executed_workers, no_construct_only_rejection |
| drone | outcome_independent_of_fixture_input | failed: action_normalized_from_task, negative_control:different_task_gives_different_result |
| ultra_review | capability_never_invoked | failed: planted_eval_input_flagged |
| autoreason | invoked_with_evidence_and_artifact_assertions_passed |  |
| ddtree | invoked_with_evidence_and_artifact_assertions_passed |  |
| lancedb | invoked_with_evidence_and_artifact_assertions_passed |  |
| memory | invoked_with_evidence_and_artifact_assertions_passed |  |
| mempalace_gate | invoked_with_evidence_and_artifact_assertions_passed |  |
| belief | invoked_with_evidence_and_artifact_assertions_passed |  |
| artifact_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| claim_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| delivery_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| acceptance_check | invoked_with_evidence_and_artifact_assertions_passed |  |
| pregate | invoked_with_evidence_and_artifact_assertions_passed |  |
| forecast_gate | invoked_with_evidence_and_artifact_assertions_passed |  |
| plan_quality_gate | invoked_with_evidence_and_artifact_assertions_passed |  |
| sandbox | invoked_with_evidence_and_artifact_assertions_passed |  |
| harness_preflight_sensor | invoked_with_evidence_and_artifact_assertions_passed |  |
| committee | capability_never_invoked | failed: verdicts_recorded, winner_or_abstain, negative_control:single_candidate_blocks |
| xray | invoked_with_evidence_and_artifact_assertions_passed |  |
| metabolism | invoked_with_evidence_and_artifact_assertions_passed |  |
| meta_opt | invoked_with_evidence_and_artifact_assertions_passed |  |
| local_model_executor | executor_or_runtime_blocked | failed: candidate_delivered_to_runtime |
| repair_loop | executor_or_runtime_blocked | failed: candidate_delivered_to_runtime, verifier_passed_on_candidate |
| semantic_failure_sensor | invoked_with_evidence_and_artifact_assertions_passed |  |
| bdd_acceptance_skill | invoked_with_evidence_and_artifact_assertions_passed |  |
| jit_validation | executor_uses_hard_coded_inputs:Mock@nexus/core/jit_tool_injector.py:23 |  |
| semantic_searcher | invoked_with_evidence_and_artifact_assertions_passed |  |
| prompt_compression | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| asi_constraint_extractor | invoked_with_evidence_and_artifact_assertions_passed |  |
| architecture_scout | outcome_independent_of_fixture_input | failed: scout_plan_ready, negative_control:different_task_changes_status |
| formal_report | invoked_with_evidence_and_artifact_assertions_passed |  |
| learn_mode | outcome_independent_of_fixture_input | failed: seeded_project_claims_counted, negative_control:unseeded_project_changes_claims_count |
| learn_phase_slo | outcome_independent_of_fixture_input | failed: seeded_writebacks_counted, missing_writebacks_fail_slo, negative_control:unseeded_project_changes_phase_slo_pass |
| file_lock | invoked_with_evidence_and_artifact_assertions_passed |  |
| direct_mode | execution_contract_has_no_runnable_physical_callable |  |
| msa_router | execution_contract_has_no_runnable_physical_callable |  |
| research_control_plane | execution_contract_has_no_runnable_physical_callable |  |
| swarm_quiet_moment | outcome_independent_of_fixture_input | failed: negative_control:event_differs_beyond_echoed_reason |
| integration_manager | executor_or_runtime_blocked |  |
| autonomic_router | invoked_with_evidence_and_artifact_assertions_passed |  |
| judge_panel | executor_or_runtime_blocked |  |
| llm_judge_panel | planner_reasons=available_but_not_selected;state=optional |  |
| external_doc_scout | execution_contract_has_no_runnable_physical_callable |  |
| learn_scheduler | executor_or_runtime_blocked | failed: scheduler_exit_zero |
| registry_sync | gate_passed_without_checkable_effect:peer_actually_reachable | failed: peer_actually_reachable |
| federation | federation (archive PR) |  |
| oracle_shadow | aos_oracle / oracle promote (archive PR) |  |
| stress_test | stress_test + _exec_stress_test (archive PR) |  |
| ui_validator | ui_explorer / ui-validator + _exec_ui_validator (archive PR) |  |
| benchmark | benchmark_service + _exec_benchmark (archive PR) |  |
| learning_closure | _exec_learning_closure (archive PR; executor only, not a planner node) |  |

## Extension 2026-10-13 (#1892): the 22 remaining planner nodes

| node | verdict | selected under production defaults? | finding |
|---|---|---|---|
| semantic_failure_sensor | REAL | no, forced only (no enable rule) | seeded lesson found (hit_count 1 vs 0); runs on the process cwd, not workspace_root; only hit_count reaches the receipt |
| bdd_acceptance_skill | REAL | no, forced only (no enable rule) | delegates to acceptance_check; passes with the real verifier, fails with a failing one |
| jit_validation | SIMULATED | yes (jit_validation_signal) | mask is a self-declared mock (`# 標籤化篩選 (Mock 實作：僅示範隔離效果)`, jit_tool_injector.py:23): Chinese keywords only, else all_tools[:5]; quota check is real |
| semantic_searcher | REAL | yes (runtime_semantic_search_signal) | FTS hit on the seeded policy card, none for an unrelated query |
| prompt_compression | REAL_UNATTESTED | no, forced only (rule input `route.prompt_compression` dropped by the planning seam) | runtime-owned edge, not `_exec_prompt_compression`; the compressed context is what the online channel receives; receipt comes from the runtime, so unattested |
| asi_constraint_extractor | REAL | yes (blocked_assumptions_require_cross_task_constraint_check) | 1 constraint from two same-family discards, 0 from two different families; records only from the request |
| architecture_scout | STUB | yes (architecture_scout_runtime_plan_required) | executor hard-codes `plateau={"reason": "mainchain_bind", ...}` without `detected`, so the planner always returns SKIPPED plateau_not_detected and the gate passes |
| formal_report | REAL | yes (formal_or_public_report_requires_evidence_report) | READY/PASS with seeded votes+verification+route receipt, BLOCKED when verification fails; all inputs must come from the request |
| learn_mode | STUB | yes (claim_or_citation_learning_signal) | reads `<cwd>/.nexus/runtime/<task_id>` (new, empty) instead of the project knowledge: claims_count 0 although the project has 2 (probe) |
| learn_phase_slo | STUB | yes (learn_phase_policy_needed) | same empty per-task run_root, window=1: phase_slo_pass is always true (project-level report: false, 3 writebacks) |
| file_lock | REAL | yes (multi_agent_write_boundary) | lock file written and checked; but one lock file per task id, so a second task locking the same file is not refused (probe) |
| direct_mode | NOT_EXECUTABLE:control_plane_reference | no, forced only (rule input `route.recommended_flow` dropped by the planning seam) | contract physical_callable=None, executor key `direct_master_loop` not in EXECUTOR_REGISTRY -> BLOCKED_EXECUTOR_UNAVAILABLE when triggered |
| msa_router | NOT_EXECUTABLE:control_plane_reference | no, forced only (rule input `route.msa_routing` dropped by the planning seam) | contract physical_callable=None, no executor -> BLOCKED_EXECUTOR_UNAVAILABLE |
| research_control_plane | NOT_EXECUTABLE:control_plane_reference | no, forced only (research_control_or_experiment_signal,tier_l1_cost_control) | contract physical_callable=None, no executor -> BLOCKED_EXECUTOR_UNAVAILABLE |
| swarm_quiet_moment | STUB | yes (swarm_write_boundary_required) | builds a pause-event dict that echoes the task text; nothing pauses, persists or reads it |
| integration_manager | BLOCKED_LEGACY_INTEGRATION_PATH_RETIRED_USE_CONTROLLED_INTEGRATION | yes (integration_or_merge_signal) | retired quarantine: always BLOCKED, mutation_performed=False |
| autonomic_router | REAL | no, forced only (no enable rule) | AutonomicRouter.route really runs (research_first vs standard by task text) but the suggestion is consumed by nothing (consumer_effect NONE) |
| judge_panel | BLOCKED_EXTERNAL_AUTH:no_judge_provider_configured | yes (evidence_quality_judge_required_for_uncertain_or_multi_candidate_route) | production default BLOCKED_EXTERNAL_AUTH; authorized it still blocks: providers are only fake / gemini / codex CLIs, no Ollama (M5) provider; ranks one hard-coded candidate c0 |
| llm_judge_panel | NOT_SELECTABLE | no, forced only (no enable rule) | never selected, even forced (state optional); direct call = judge_panel alias, same blocks |
| external_doc_scout | NOT_EXECUTABLE:no_live_connector | yes (claim_uncertainty_requires_external_fact_check) | contract physical_callable=None; executor is an auth gate that returns BLOCKED no_live_connector once authorized |
| learn_scheduler | BLOCKED_scheduler_exit_2 | no, forced only (no enable rule) | runs `learn:phase-policy` in the code checkout (hard-coded `repo_root = Path(__file__).resolve().parents[2]`), PassRate 0% there -> exit 2 |
| registry_sync | STUB | yes (platform_registry_signal) | with the external flag and a loopback port with no listener: VERIFIED, peer_contacted=True, row_count=0 (pull_from_peer swallows the connection error) |

Not selected under production defaults (forced only): semantic_failure_sensor, bdd_acceptance_skill, autonomic_router, learn_scheduler, llm_judge_panel (no enable rule); prompt_compression, direct_mode, msa_router (their rule reads a `route` key the planning seam drops); research_control_plane (enabled by its signal, then demoted to optional by `tier_l1_cost_control`). The others are selected by a production rule but, except jit_validation and semantic_searcher, are escalate-gated: selected and then skipped (`SKIPPED_POLICY_NOT_TRIGGERED`) unless `route.escalate_triggered` is set, which `nexus run` does not do.

## Executor-registry keys with no planner node

17 keys (computed: `EXECUTOR_REGISTRY` minus planner nodes, aliases and contract executor keys; unlisted=[], listed-but-reachable=[]). All are `UNREACHABLE_NO_PLANNER_NODE`. Kinds: `{"ALIAS": 1, "AUTH_GATED_REAL_CALL": 1, "REAL_CALL": 1, "REAL_CALL_CONSTANT_INPUTS": 1, "REAL_CALL_DEGRADED": 1, "REAL_CALL_FIXTURE_INPUTS": 2, "REAL_CALL_HARD_CODED_TMP": 1, "REAL_CALL_MISUSED_INPUT": 1, "STUB_CONSTANT_STATUS": 1, "STUB_CONSTRUCT_ONLY": 7}`. Invoked directly under production default; two of them wrote to the shared `/tmp`: policy_capability_gate (`/tmp/.nexus/knowledge/policy_memory.jsonl`) and reflex_loop (`/tmp/.nexus/config/reflex_params.json`).

| executor key | verdict | kind | gate_passed | what it does | quoted line(s) |
|---|---|---|---|---|---|
| aos_oracle | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTANT_STATUS | True | AosService(repo_root=/tmp).get_status() returns the literal {'status': 'OPERATIONAL', 'aos_version': '145.2', 'trust_score': 0.98, 'governance': 'ACTIVE'} (a... | `inst = cls(repo_root=Path("/tmp"))` (:1036) |
| attempt_settlement_service | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTRUCT_ONLY | False | constructs AttemptSettlementService with /tmp paths, zero metrics and transaction_mgr={'status': 'simulated'}; rejected as import_construct_not_execution | `run_dir=Path("/tmp/run"),` (:2074); `transaction_mgr={"status": "simulated"},` (:2077) |
| battle_swarm | UNREACHABLE_NO_PLANNER_NODE | ALIAS | False | delegates to _exec_swarm_multi_agent (same body as the swarm / multi_agent rows); auth-blocked at production default | `return _exec_swarm_multi_agent(plan, task_desc)` (:1537) |
| decision_formula_engine | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTRUCT_ONLY | False | constructs DecisionFormulaEngine(context=...) and reports class_instantiated; no formula evaluated; rejected as import_construct_not_execution | `outcome={"class_instantiated": True, "context_keys": list(context.keys())})` (:749) |
| dual_loop | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTRUCT_ONLY | False | constructs DualLoopOrchestrator(project_root=/tmp) and reports class_instantiated; rejected as import_construct_not_execution | `inst = cls(project_root="/tmp")` (:1623); `outcome={"class_instantiated": True})` (:1626) |
| entropy_guard_v2 | UNREACHABLE_NO_PLANNER_NODE | REAL_CALL | True | EntropyGuardV2().audit_payload(task_desc); outcome keeps only entropy_ok (defaults True) | `outcome={"entropy_ok": result.get("passed", True)})` (:515) |
| learn_refresh_service | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTRUCT_ONLY | False | constructs LearnRefreshService(repo_root=/tmp) and reports class_instantiated; no refresh runs; the registry's construct-only guard then rejects it (import_c... | `inst = cls(repo_root=Path("/tmp"))` (:1055); `outcome={"class_instantiated": True})` (:1058) |
| mfp_gate | UNREACHABLE_NO_PLANNER_NODE | REAL_CALL_CONSTANT_INPUTS | True | evaluate_mfp with constant confidence=0.99, semantic_entropy=0.1, history_success_rate=0.96, so it always returns passed=True (input-independent) | `result = fn(confidence=0.99, semantic_entropy=0.1, history_success_rate=0.96)` (:2019) |
| nightshift_runner_service | UNREACHABLE_NO_PLANNER_NODE | AUTH_GATED_REAL_CALL | False | same body as the nightshift row (nightshift aliases it); blocked without NEXUS_LOCAL_MODEL_CALL_ALLOWED / NEXUS_EXTERNAL_RUNTIME_AUTHORIZED; default target R... | `target_file = str(constraints.get("nightshift_target_file") or "README.md")` (:559) |
| policy_capability_gate | UNREACHABLE_NO_PLANNER_NODE | REAL_CALL_FIXTURE_INPUTS | True | calls nexus.services.policy_gate.apply_policy_gate with fixed health metrics and repo_root=/tmp (writes /tmp/.nexus/knowledge/policy_memory.jsonl); returns s... | `health_metrics={"memory_usage": 0.5, "cpu_usage": 0.3, "error_rate": 0.01},` (:492); `repo_root=Path("/tmp"),` (:493) |
| predictive_auditor | UNREACHABLE_NO_PLANNER_NODE | REAL_CALL_DEGRADED | True | PredictiveAuditor().audit_risk({task_id, constraints}); with no Wisdom Registry table it returns risk_score 0.0 / PROCEED (with a table it would embed locall... | `outcome={"risk_score": str(result.get("risk_score", "N/A"))[:100]})` (:708) |
| promotion_engine | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTRUCT_ONLY | False | constructs PromotionEngine() and reports class_instantiated; rejected as import_construct_not_execution | `outcome={"class_instantiated": True})` (:2039) |
| reflex_loop | UNREACHABLE_NO_PLANNER_NODE | REAL_CALL_HARD_CODED_TMP | True | ReflexLoop(project_root=/tmp).run_cycle(): NAS tuner + BattleSwarm tuning against /tmp logs; writes /tmp/.nexus/config/reflex_params.json | `inst = cls(project_root="/tmp")` (:1129) |
| research_and_source_discipline | UNREACHABLE_NO_PLANNER_NODE | REAL_CALL_MISUSED_INPUT | True | PythonCodeSkeletonProvider(root=cwd).lookup_implementation(<whole task text>) - the task sentence is looked up as a symbol name | `result = inst.lookup_implementation(str(task_desc or plan.task_id))` (:1004) |
| spec_guarded | UNREACHABLE_NO_PLANNER_NODE | REAL_CALL_FIXTURE_INPUTS | True | SpecGuardV2().validate_diagnosis({'task_id'}, constraints) with an empty diagnosis and empty constraints; reports validated (defaults True) | `result = inst.validate_diagnosis({"task_id": plan.task_id}, dict(plan.constraints))` (:723); `outcome={"validated": str(result.get("validated", True))})` (:726) |
| subagent_outcome_service | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTRUCT_ONLY | False | constructs SubagentOutcomeService(project_root=/tmp) and reports class_instantiated; rejected as import_construct_not_execution | `inst = cls(project_root=Path("/tmp"))` (:2054); `outcome={"class_instantiated": True})` (:2057) |
| zero_trust_v2_behavior | UNREACHABLE_NO_PLANNER_NODE | STUB_CONSTRUCT_ONLY | True | builds the behavior runner adapter and returns function_called=True (gate passes); the adapter is never run | `outcome={"function_called": True})` (:530) |

## REAL_UNATTESTED today

artifact_gate, claim_gate, delivery_gate (postflight invoker) and prompt_compression (runtime-owned compression edge): the effect is real and checked, but the receipt is produced by nexus-runtime, where the Nexus-side attestation (batch 1) does not reach; the runtime producer fix is still needed.

## Wiring-fix backlog (code location that makes each non-real)

| capability | verdict | location and cause |
|---|---|---|
| all receipts | producer cannot attest execution | `nexus_runtime` `CapabilityReceipt.to_dict()` / `build_trace_receipts` never set `claim_boundary.simulated`; fix in nexus-runtime. |
| research, research_route | STUB / BLOCKED | `capability_executor_registry.py:850` (_exec_research) passes `task_statement`; `ResearchPhaseHandler.run` reads `context["task"]`, so output is always "Empty research task.". research_route additionally fails the contract (`missing_outcome_field:control_plane_reference`), is selected on every run and skipped unless triggered. |
| hyper | BLOCKED | `:1245` outcome lacks semantic_status/evidence_refs so the invoker rejects it (`execution_contract_violation`); config fixes candidate_count=1, target README.md, llm_mode=False. |
| nightshift | BLOCKED | `:511/1400` one round, bare task; phase policy denies research at PassRate=0% (`NightShift Blocked by Phase Policy`), no report written. |
| swarm, multi_agent | BLOCKED | `:1296` only constructs BattleSwarm and calls cleanup; rejected as `import_construct_not_execution`. |
| drone | STUB | `:1341` repair_response_schema/normalize_action on task text; gate passes for any input, no sub-task. |
| ultra_review | BLOCKED (product path), STUB (executor) | planner demands role `independent_review` (L2+) that the admitted online worker lacks; executor `:1700` only captures git diff (`_scan_security_observations` never called, planted eval(input()) unflagged; component probe shows the scanner exists). |
| autoreason, ddtree | SIMULATED | `:1154` / `:2402` rank/plan one hard-coded candidate c0; BLOCKED_EXTERNAL_AUTH at production default; component probes: Autoreason ranks A>B>C (9/6/3), DDTree prunes 5 to 3 with pruned_count=2. |
| memory | STUB | `:1973` + registry allowlist: `memory_query` never fed, whole task statement used as SQL LIKE pattern. |
| harness_preflight_sensor | STUB | `:2234` pending/selected capabilities are not in the runtime capability context, so the sensor evaluates empty lists and passes vacuously. |
| committee | BLOCKED | canonical context seam forbids keys containing "model" (`committee_proposals[].model`), so proposals cannot reach the executor; controller off without `NEXUS_USE_COMMITTEE`; executor omits `attempt` which the controller indexes. |
| xray | SIMULATED | `:3549` scan target hard-coded to `nexus/services/capability_registry.py`. |
| local_model_executor, repair_loop | BLOCKED | Local stage ran 7 real model calls on the M5 (ledger with Ollama metrics, candidate edit in world-C workspace, source untouched) but `candidate_patch` was empty at the LocalAssistService boundary: `local_output_not_delivered, candidate_not_isolated, verifier_not_passed`; the capability row reports SELECTED_NOT_EXECUTED despite the calls. Not debugged further; may be fixture-specific (world-C copy contained only calc.py). Registry fallback for local_model_executor uses a fixture provider (`capability_registry.py` build_local_model_executor_invoker). |
| codeintel (gap) | REAL_UNATTESTED | executor calls only `lookup_implementation`; graph (4 nodes) and impact set (app/api.py) exist in `graph_builder`/`impact_service` but are not surfaced. |
| mempalace_gate (gap) | REAL_UNATTESTED | blacklist applies to retrieved artifacts, not tool invocations. |
| production policy | gap | planner snapshot defaults `model_call_allowed` to "1" while registry executors require the env var to be set; `nexus run` sets neither. |
| architecture_scout | STUB | `capability_executor_registry.py` `_exec_architecture_scout`: plateau dict lacks `detected`, so `DistantScoutPlanner.plan` always returns SKIPPED; gate is `isinstance(result, Mapping)`. |
| learn_mode, learn_phase_slo | STUB | `_resolve_run_root` gives `<cwd>/.nexus/runtime/<task_id>` when the request carries no `run_root`/`project_root` (the registry allowlist feeds neither), so both reports read an empty directory; gate is `result is not None`. |
| swarm_quiet_moment | STUB | `_exec_swarm_quiet_moment` returns `build_quiet_moment_event(...)`; no pause is enforced or persisted. |
| registry_sync | STUB | `nexus/security/secure_sync.py` `pull_from_peer` returns `[]` on any exception; the executor treats a list as VERIFIED with `peer_contacted=True`. |
| jit_validation | SIMULATED | `nexus/core/jit_tool_injector.py:19` `apply_mask` is a keyword mock (Chinese keywords, else first five tools). |
| file_lock (gap) | REAL | lock file keyed by task id (`.nexus/multi_agent/locks/<task_id>.json`), so there is no cross-task exclusion. |
| judge_panel | BLOCKED | no local/M5 judge provider in `nexus/engine/llm_judge_providers.py` (fake, gemini, codex only); single hard-coded candidate `c0`. |
| learn_scheduler | BLOCKED | `LearnSchedulerService(repo_root=<checkout>)` evaluates the checkout's learning data, not the task workspace. |
| direct_mode, msa_router, research_control_plane, external_doc_scout | NOT_EXECUTABLE | no physical callable in `PLANNER_EXECUTION_CONTRACTS`; three have no executor key at all. |
| executor-only keys | UNREACHABLE | 17 registry entries no planner node reaches; 8 are construct-only (rejected as `import_construct_not_execution`, or `function_called=True` for zero_trust_v2_behavior), several hard-code `/tmp` or constant inputs (table above). |

Not audited: nothing skipped except the RETIRING rows (federation, oracle_shadow, stress_test, ui_validator, benchmark, learning_closure), owned by the archive PR. Since #1892 every planner node of the pinned runtime has a row.

## capability_route_smoke.py

- On this host the smoke first failed closed with exit 78 (`LEGACY_EXTRA_REQUIRED`: bench subprocess used `uv run` without the legacy extra). Re-run with `NEXUS_BENCH_SUBPROCESS_PYTHON` set: **fails** (`passed: false`; route_oracles 8/8 rows fail with `evidence_without_gate_pass` / `selected_without_invocation` / `missing_verifier_artifact;missing_source_hash`; 14 of 15 task rows fail overall).
- It does **not** read `simulated`: its validators (and `capability_receipt_policy.py`, `gemini_nexus_report.py`) contain zero references. A synthetic with-Nexus row whose receipts all carry `claim_boundary.simulated=true` passes the row validator with no failures (`audit.smoke_probe`, covered by a test). So it fails here for gate/evidence reasons, but would pass on simulated receipts that look successful.


## Batch 1 fixes

Issue #1862 (stacks on #1861). Seven rows re-run with the same switches as the main audit (`uv run --extra legacy python scripts/ops/capability_wiring_audit.py --only research,memory,autoreason,ddtree,hyper,xray,harness_preflight_sensor`; M5 tunnel `127.0.0.1:11434`, model `qwen2.5-coder:7b-instruct`, nothing started locally). Before: run `2026-10-12T08:40:11.324859+00:00` on origin/main 1324a1e1e. After: run `2026-10-12T11:20:15.817191+00:00` on this branch. Verdict counts before `{"BLOCKED": 1, "SIMULATED": 3, "STUB": 3}`, after `{"BLOCKED": 1, "REAL": 6}`.

The audit scenarios now supply the request inputs the fixed executors read (`codeintel.autoreason_candidates`, `ddtree_candidates`, `xray_targets`, `hyper_*`, `memory_query`), because the executors no longer invent them. Unit tests: `tests/services/test_capability_wiring_fixes_batch1.py`.

| capability | before | after | receipt simulated before -> after | note |
|---|---|---|---|---|
| research | STUB | production default: BLOCKED_EXTERNAL_AUTH; with `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1`: REAL | True -> False | executor passes `task` (handler key) plus `task_statement`; per-task run dir `.nexus/research/<task_id>` (was shared `/tmp`, whose `researchpack.json` cache returned one task's pack for all); gate fails on empty task or provider `status=FAIL`. Provider egress (chub CLI / felo) is blocked unless the env switch is set (`provider_call_count=0`); URL extraction is disabled for this executor (the task is an opaque payload; nothing is parsed for endpoints); the `~/.openclaw` LanceDB cache is disabled for this executor. |
| memory | STUB | REAL | True -> False | `memory_query` now read from `codeintel`; when only a task statement exists, retrieval mirrors local_heal (exact query, then de-duplicated per-keyword lookups, oracle contract text stripped); read-only FindingsMemory episode count reported as `findings_hit_count`; empty query stays blocked. |
| autoreason | SIMULATED | REAL | True -> False | candidate pool from `codeintel.autoreason_candidates` (or `candidate_pool`) via the registry allowlist; no pool -> `skip_reason=no_candidate_pool`, never a fabricated `c0`. |
| ddtree | SIMULATED | REAL | True -> False | pool from `codeintel.ddtree_candidates`, `max_candidates` from `ddtree_max_candidates`; same `no_candidate_pool` skip. |
| hyper | BLOCKED_execution_contract_violation:missing_evidence_field:evidenc... | BLOCKED_semantic_status=FAILED | True -> False | candidate_count / target file / test file / llm_mode / repo root from the request (`hyper_*`, `target_file(s)`, `workspace_root`); outcome now has `semantic_status`, `evidence_refs`, sprint status, attempt_count; contract passes. The sprint itself still FAILS on the README fixture (`stage1_no_passing_candidate`, 3 deterministic attempts, llm_mode off by default), so the row stays blocked on `semantic_status=FAILED`, no longer on the contract. |
| xray | SIMULATED | REAL | True -> False | targets from `xray_targets` / `target_file(s)` resolved under `workspace_root`; repo root fallback; gate requires every target to exist. |
| harness_preflight_sensor | STUB | REAL | True -> False | `selected_capabilities` / `pending_capabilities` taken from the planner stage in the runtime context; a non-empty pending list now fails the gate. |

### Receipt attestation (Nexus-new side)

The pinned `nexus_runtime` `CapabilityReceipt.to_dict()` hard-codes `claim_boundary={"public_claim_allowed": False}` (belief receipt: plus `claim_eligible`), takes no argument, and `ClaimBoundary.from_dict` is not reachable from it, so there is no hook. Nexus-new therefore re-projects `receipt_base` with `project_child_receipt_base(..., claim_boundary=<evaluated ClaimBoundary>)` in `nexus/engine/capability_receipts.py` (`attested_receipt_dict`, `evaluate_receipt_claim_boundary`, `build_attested_trace_receipts`); `nexus/core/router.py` uses it for executor receipts, and the wiring audit uses it for `receipt_claims_simulated`. `simulated=False` only when the receipt is `invoked`, has evidence refs, and the outcome is not an auth block / skip / import-construct result / error; otherwise it stays true. `public_claim_allowed` stays false (`ClaimBoundary.evaluate` never unlocks it); `receipt_hash` is recomputed because it covers the boundary. Trace receipts built by `build_trace_receipts` stay `simulated=true` unless the caller passes executor outcomes. The runtime producer still needs a fix (`to_dict` should accept a claim boundary); this is a Nexus-new post-processing step until it lands. Because REAL is defined by `simulated=false`, the six rows above are REAL rather than REAL_UNATTESTED; the audit now reads the attested receipt, so rows that were REAL_UNATTESTED above (codeintel, lancedb, ...) would re-measure as REAL; they were not re-run in this batch and the main matrix above is left as the historical 929a953d0 record.

### Not changed

research needs `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1` for any outbound call (provider `auto`: the `chub` CLI against its public CDN with no credential in the code path, falling back to `npx @willh/felo-cli`, which would use `FELO_API_KEY` from the environment); the authorized positive audit run used chub. swarm / multi_agent, committee, ultra_review, nightshift and the Local stage empty `candidate_patch` are out of scope for this batch.

### Containment and authorization

The registry forwards `workspace_root` to hyper/xray only from the runtime context or route, never from request `codeintel`; research takes no root and uses the project root. Every request-named hyper target/test file and xray target must resolve inside that root and exist (else blocked `path_outside_workspace`); with no xray target the legacy `nexus/services/capability_registry.py` (if present) or the root is scanned. hyper `llm_mode` from the request still requires `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1`; constraint flags such as `allow_fixture_model_boundary` are not on any allowlist and do not authorize autoreason/ddtree.
