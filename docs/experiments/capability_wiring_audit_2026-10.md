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

Verdict counts, all 58 rows (57 planner nodes + the `learning_closure` executor): `{"BLOCKED": 9, "NOT_EXECUTABLE": 4, "REAL": 30, "REAL_UNATTESTED": 4, "RETIRING": 9, "SIMULATED": 1, "STUB": 1}`.

- The 36 rows audited before: `{"BLOCKED": 9, "REAL": 17, "REAL_UNATTESTED": 3, "RETIRING": 6, "STUB": 1}`, identical to the post-batch-1 run (`{"BLOCKED": 9, "REAL": 17, "REAL_UNATTESTED": 3, "RETIRING": 6, "STUB": 1}`, run 2026-10-12T13:19:36 on origin/main 4dbac7875 + #1862). History: at 929a953d0 they were 14 REAL_UNATTESTED, 4 STUB, 3 SIMULATED, 9 BLOCKED, 6 RETIRING, 0 REAL.
- The 22 new rows: `{"BLOCKED": 3, "NOT_EXECUTABLE": 4, "NOT_SELECTABLE": 1, "REAL": 7, "REAL_UNATTESTED": 1, "SIMULATED": 1, "STUB": 5}`.
- Second archive batch (#1906, partial rerun 2026-10-13T00:00:33.434238+00:00): integration_manager, swarm_quiet_moment and llm_judge_panel now read RETIRING with their `archived_*_2026-10-13` skip reasons; counts over the same 58 rows become `{"BLOCKED": 11, "NOT_EXECUTABLE": 4, "REAL": 24, "REAL_UNATTESTED": 4, "RETIRING": 9, "SIMULATED": 1, "STUB": 5}` (the `.matrix.json` rows were replaced in place; see its `partial_reruns`).
- Second-batch wiring fixes (partial rerun 2026-10-13T04:16:04.237470+00:00, `--only learn_mode,learn_phase_slo,learn_scheduler,file_lock,registry_sync,jit_validation,nightshift` on origin/main fe29afcee + the fix working tree; no model call): learn_mode STUB -> REAL, learn_phase_slo STUB -> REAL, learn_scheduler BLOCKED_scheduler_exit_2 -> REAL, registry_sync STUB -> BLOCKED_REGISTRY_PEER_UNAVAILABLE:ConnectionRefusedError (fail closed; no live peer in the fixture), file_lock REAL -> REAL (second task now refused), jit_validation SIMULATED -> SIMULATED (receipt now says so), nightshift BLOCKED -> BLOCKED (reason now `SLO=phase_slo_summary_missing`). Counts over the 58 rows: `{"BLOCKED": 11, "NOT_EXECUTABLE": 4, "REAL": 27, "REAL_UNATTESTED": 4, "RETIRING": 9, "SIMULATED": 1, "STUB": 2}`.
- Group D (#1981, partial rerun 2026-10-13T04:52:33.902428+00:00 on origin/main fe29afcee + the group D tree): ultra_review, judge_panel and architecture_scout now read REAL; direct_mode, msa_router, research_control_plane and external_doc_scout stay NOT_EXECUTABLE but their receipts now say so (`observed_verdict` `BLOCKED_NOT_EXECUTABLE:<reason>`, was `BLOCKED_EXECUTOR_UNAVAILABLE` / an auth gate). Counts over the same 58 rows: `{"BLOCKED": 9, "NOT_EXECUTABLE": 4, "REAL": 27, "REAL_UNATTESTED": 4, "RETIRING": 9, "SIMULATED": 1, "STUB": 4}` (batch 2, #1973, is not merged into this matrix; see "Group D fixes" below).

`research` is BLOCKED_EXTERNAL_AUTH at production default and REAL only with `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1`; `judge_panel`, `external_doc_scout` and `registry_sync` likewise record both attempts (see `policy_attempts` in the `.matrix.json`; the table shows the best verdict). federation, oracle_shadow, stress_test, ui_validator and benchmark are retired at planner level in the pinned runtime; learning_closure is an executor, not a planner node. Full strings are in the `.matrix.json`.

| capability | verdict | executor-level verdict (product path blocked) | production default, selected but untriggered | selected without forcing (production defaults) | executor (function @ file:line) | reached via | switches needed | receipt_claims_simulated |
|---|---|---|---|---|---|---|---|---|
| codeintel | REAL | - | - | - | _exec_codeintel @ nexus/core/capability_executor_registry.py:758 | EXECUTOR_REGISTRY | none | False |
| research | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_research @ nexus/core/capability_executor_registry.py:876 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| research_route | BLOCKED_execution_contract_violation:missing_outcome_field:control_plane_reference | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_research @ nexus/core/capability_executor_registry.py:876 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| hyper | BLOCKED_semantic_status=FAILED | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_hyper_sprint @ nexus/core/capability_executor_registry.py:1332 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | False |
| nightshift | BLOCKED_semantic_status=BLOCKED(terminal_status=FAILED):console:❌ [NightShift] Blocked by Phase Policy: PassRate=0.0%... | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_nightshift @ nexus/core/capability_executor_registry.py:1350 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| swarm | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1427 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| multi_agent | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1427 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| drone | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_drone @ nexus/core/capability_executor_registry.py:1472 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| ultra_review | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | - | _exec_ultra_review @ nexus/core/capability_executor_registry.py:1628 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
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
| jit_validation | SIMULATED | - | - | yes: jit_validation_signal | _exec_jit_validation @ nexus/core/capability_executor_registry.py:2527 | EXECUTOR_REGISTRY | none | False |
| semantic_searcher | REAL | - | - | yes: runtime_semantic_search_signal | _exec_semantic_searcher @ nexus/core/capability_executor_registry.py:2241 | EXECUTOR_REGISTRY | none | False |
| prompt_compression | REAL_UNATTESTED | - | - | no (optional; rule input dropped by seam: prompt_compression; available_but_not_selected) | build_prompt_compression_capability_invoker @ nexus_runtime/kernel/capabilities.py:408 | RUNTIME_INVOKER | none | True |
| asi_constraint_extractor | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: blocked_assumptions_require_cross_task_constraint_check | _exec_asi_constraint_extractor @ nexus/core/capability_executor_registry.py:3097 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| architecture_scout | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: architecture_scout_runtime_plan_required | _exec_architecture_scout @ nexus/core/capability_executor_registry.py:2875 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| formal_report | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: formal_or_public_report_requires_evidence_report | _exec_formal_report @ nexus/core/capability_executor_registry.py:3480 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| learn_mode | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: claim_or_citation_learning_signal | _exec_learn_mode @ nexus/core/capability_executor_registry.py:2309 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| learn_phase_slo | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: learn_phase_policy_needed | _exec_learn_phase_slo @ nexus/core/capability_executor_registry.py:2372 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| file_lock | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: multi_agent_write_boundary | _exec_file_lock @ nexus/core/capability_executor_registry.py:3008 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| direct_mode | NOT_EXECUTABLE:control_plane_reference | - | NOT_EXECUTABLE:control_plane_reference | no (optional; rule input dropped by seam: recommended_flow; available_but_not_selected) | - | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| msa_router | NOT_EXECUTABLE:control_plane_reference | - | NOT_EXECUTABLE:control_plane_reference | no (optional; rule input dropped by seam: msa_routing; available_but_not_selected) | - | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| research_control_plane | NOT_EXECUTABLE:control_plane_reference | - | NOT_EXECUTABLE:control_plane_reference | no (optional; research_control_or_experiment_signal,tier_l1_cost_control) | - | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| swarm_quiet_moment | RETIRING | - | - | - | - | - | none | None |
| integration_manager | RETIRING | - | - | - | - | - | none | None |
| autonomic_router | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; available_but_not_selected) | _exec_autonomic_router @ nexus/core/capability_executor_registry.py:636 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| judge_panel | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: evidence_quality_judge_required_for_uncertain_or_multi_candidate_route | _exec_judge_panel @ nexus/core/capability_executor_registry.py:2732 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | False |
| llm_judge_panel | RETIRING | - | - | - | - | - | none | None |
| external_doc_scout | NOT_EXECUTABLE:no_live_connector | - | NOT_EXECUTABLE:no_live_connector | yes: claim_uncertainty_requires_external_fact_check | _exec_external_doc_scout @ nexus/core/capability_executor_registry.py:3791 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| learn_scheduler | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | no (optional; available_but_not_selected) | _exec_learn_scheduler_service @ nexus/core/capability_executor_registry.py:900 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| registry_sync | BLOCKED_REGISTRY_PEER_UNAVAILABLE:ConnectionRefusedError:console:mTLS pull from 127.0.0.1:63185 failed: [Errno 61] Co... | - | SKIPPED_POLICY_NOT_TRIGGERED | yes: platform_registry_signal | _exec_registry_sync @ nexus/core/capability_executor_registry.py:3376 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | True |
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
| ultra_review | invoked_with_evidence_and_artifact_assertions_passed |  |
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
| architecture_scout | invoked_with_evidence_and_artifact_assertions_passed |  |
| formal_report | invoked_with_evidence_and_artifact_assertions_passed |  |
| learn_mode | invoked_with_evidence_and_artifact_assertions_passed |  |
| learn_phase_slo | invoked_with_evidence_and_artifact_assertions_passed |  |
| file_lock | invoked_with_evidence_and_artifact_assertions_passed |  |
| direct_mode | execution_contract_has_no_runnable_physical_callable |  |
| msa_router | execution_contract_has_no_runnable_physical_callable |  |
| research_control_plane | execution_contract_has_no_runnable_physical_callable |  |
| swarm_quiet_moment | archived_echo_swarm_quiet_moment_2026-10-13 (second archive batch) |  |
| integration_manager | archived_retired_integration_manager_2026-10-13 (second archive batch) |  |
| autonomic_router | invoked_with_evidence_and_artifact_assertions_passed |  |
| judge_panel | invoked_with_evidence_and_artifact_assertions_passed |  |
| llm_judge_panel | archived_alias_llm_judge_panel_2026-10-13 (second archive batch) |  |
| external_doc_scout | execution_contract_has_no_runnable_physical_callable |  |
| learn_scheduler | invoked_with_evidence_and_artifact_assertions_passed |  |
| registry_sync | executor_or_runtime_blocked |  |
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
| jit_validation | SIMULATED | yes (jit_validation_signal) | mask is a self-declared mock (`# 標籤化篩選 (Mock 實作：僅示範隔離效果)`, jit_tool_injector.py:23): Chinese keywords only, else all_tools[:5]; quota check is real; since 2026-10-13 the receipt carries `simulated=True`, `mask_kind=keyword_mock`, `claim_boundary.claim=SIMULATED` |
| semantic_searcher | REAL | yes (runtime_semantic_search_signal) | FTS hit on the seeded policy card, none for an unrelated query |
| prompt_compression | REAL_UNATTESTED | no, forced only (rule input `route.prompt_compression` dropped by the planning seam) | runtime-owned edge, not `_exec_prompt_compression`; the compressed context is what the online channel receives; receipt comes from the runtime, so unattested |
| asi_constraint_extractor | REAL | yes (blocked_assumptions_require_cross_task_constraint_check) | 1 constraint from two same-family discards, 0 from two different families; records only from the request |
| architecture_scout | REAL (was STUB) | yes (architecture_scout_runtime_plan_required) | group D: plateau from `runtime_decision.detect_plateau` over the request's `asi_failure_records`; READY plan only after 4 same-family discards, `PLATEAU_NOT_DETECTED:<reason>` otherwise (was: hard-coded plateau without `detected`, always SKIPPED, gate passed) |
| formal_report | REAL | yes (formal_or_public_report_requires_evidence_report) | READY/PASS with seeded votes+verification+route receipt, BLOCKED when verification fails; all inputs must come from the request |
| learn_mode | REAL (was STUB) | yes (claim_or_citation_learning_signal) | fixed 2026-10-13: reads the project learn store `LearnModeService(<workspace_root>)` like `learn:*`; seeded project counts its claims, unseeded counts 0. Was: `<cwd>/.nexus/runtime/<task_id>` (new, empty), claims_count 0 although the project had 2 |
| learn_phase_slo | REAL (was STUB) | yes (learn_phase_policy_needed) | fixed 2026-10-13: project phase ledger, CLI window 300; seeded ledger gives phase_slo_pass false with 3 writebacks, unseeded true. Was: empty per-task run_root, window=1, always true |
| file_lock | REAL | yes (multi_agent_write_boundary) | fixed 2026-10-13: one flock-guarded registry per workspace keyed by file (holder = task id); the probe's second task is BLOCKED `FILE_LOCK_HELD_BY_OTHER_TASK:target.py@lock-task-a`, same-task re-lock idempotent, 1800 s TTL for stale locks. Was: one lock file per task id, no cross-task exclusion |
| direct_mode | NOT_EXECUTABLE:control_plane_reference | no, forced only (rule input `route.recommended_flow` dropped by the planning seam) | contract physical_callable=None, executor key `direct_master_loop` not in EXECUTOR_REGISTRY; since group D the receipt is an explicit skip `NOT_EXECUTABLE:control_plane_reference` (was BLOCKED_EXECUTOR_UNAVAILABLE when triggered) |
| msa_router | NOT_EXECUTABLE:control_plane_reference | no, forced only (rule input `route.msa_routing` dropped by the planning seam) | contract physical_callable=None, no executor; receipt `NOT_EXECUTABLE:control_plane_reference` since group D (an executor is an MSA design task) |
| research_control_plane | NOT_EXECUTABLE:control_plane_reference | no, forced only (research_control_or_experiment_signal,tier_l1_cost_control) | contract physical_callable=None, no executor; receipt `NOT_EXECUTABLE:control_plane_reference` since group D |
| swarm_quiet_moment | RETIRING (was STUB) | yes (swarm_write_boundary_required) | archived 2026-10-13 (#1906): receipt skip reason `archived_echo_swarm_quiet_moment_2026-10-13`; it built a pause-event dict that echoed the task text, nothing paused, persisted or read it |
| integration_manager | RETIRING (was BLOCKED_LEGACY_INTEGRATION_PATH_RETIRED_USE_CONTROLLED_INTEGRATION) | yes (integration_or_merge_signal) | archived 2026-10-13 (#1906): receipt skip reason `archived_retired_integration_manager_2026-10-13`; it was a retired quarantine, always BLOCKED, mutation_performed=False |
| autonomic_router | REAL | no, forced only (no enable rule) | AutonomicRouter.route really runs (research_first vs standard by task text) but the suggestion is consumed by nothing (consumer_effect NONE) |
| judge_panel | REAL with `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1` (was BLOCKED_EXTERNAL_AUTH:no_judge_provider_configured) | yes (evidence_quality_judge_required_for_uncertain_or_multi_candidate_route) | group D: `OllamaJudgeProvider` (Workforce `local_first.classification` -> `local_qwen35_9b` = qwen3.5:9b on M5) ranks the request's candidate pool (`codeintel.judge_panel_candidates`); fixture 3 candidates with neutral ids, winner cand-b, swapped content moves it to cand-a; production default still BLOCKED_EXTERNAL_AUTH |
| llm_judge_panel | RETIRING (was NOT_SELECTABLE) | no, forced only (no enable rule) | archived 2026-10-13 (#1906): receipt skip reason `archived_alias_llm_judge_panel_2026-10-13`; it was never selected, even forced, and a direct call was the judge_panel alias |
| external_doc_scout | NOT_EXECUTABLE:no_live_connector | yes (claim_uncertainty_requires_external_fact_check) | contract physical_callable=None; since group D the planner-node invoker never calls the auth-gate executor and the receipt says `NOT_EXECUTABLE:no_live_connector` |
| learn_scheduler | REAL (was BLOCKED_scheduler_exit_2) | no, forced only (no enable rule) | fixed 2026-10-13: `learn:phase-policy --project-root <workspace_root>`; passing workspace ledger -> exit 0, none -> exit 2. Was: evaluated the code checkout, and the phase policy read a never-written `overall_pass_rate` key, so PassRate was 0% everywhere |
| registry_sync | BLOCKED_REGISTRY_PEER_UNAVAILABLE:ConnectionRefusedError (was STUB) | yes (platform_registry_signal) | fixed 2026-10-13: `pull_from_peer_checked`; loopback port with no listener -> BLOCKED, peer_contacted=False. Was: VERIFIED, peer_contacted=True, row_count=0. No positive run (no live mTLS peer in the fixture) |

Not selected under production defaults (forced only): semantic_failure_sensor, bdd_acceptance_skill, autonomic_router, learn_scheduler, llm_judge_panel (no enable rule); prompt_compression, direct_mode, msa_router (their rule reads a `route` key the planning seam drops); research_control_plane (enabled by its signal, then demoted to optional by `tier_l1_cost_control`). The others are selected by a production rule but, except jit_validation and semantic_searcher, are escalate-gated: selected and then skipped (`SKIPPED_POLICY_NOT_TRIGGERED`) unless `route.escalate_triggered` is set, which `nexus run` does not do.

## Executor-registry keys with no planner node

Second archive batch (2026-10-13, #1906, `ARCHIVED_2026-10-13.md`): all 17 keys were removed from `EXECUTOR_REGISTRY` and the audit now reports them `RETIRING` (`archived_executor_only_no_planner_node_2026-10-13`) without invoking anything; the "what it does" column is the 2026-10-12 finding that justified the retirement. `entropy_guard_v2` lost only its dead key (module `nexus/services/entropy_v2.py` kept; planner node + fixture tracked in #1907); `nightshift_runner_service` and `battle_swarm` were aliases (the nightshift and swarm/multi_agent nodes keep their executors); `nexus/services/policy_gate.py` stays for the legacy self_heal_selector. Partial rerun 2026-10-13T00:00:33.434238+00:00: `--only integration_manager,swarm_quiet_moment,llm_judge_panel,executor_only --no-model` on origin/main 3976f1d0f + the #1906 working tree (no model needed); the computed executor-only set is now empty apart from the first-batch `learning_closure` (RETIRING).

Before the archive (run 2026-10-12T22:57:52): 17 keys, all `UNREACHABLE_NO_PLANNER_NODE`, kinds `{"ALIAS": 1, "AUTH_GATED_REAL_CALL": 1, "REAL_CALL": 1, "REAL_CALL_CONSTANT_INPUTS": 1, "REAL_CALL_DEGRADED": 1, "REAL_CALL_FIXTURE_INPUTS": 2, "REAL_CALL_HARD_CODED_TMP": 1, "REAL_CALL_MISUSED_INPUT": 1, "STUB_CONSTANT_STATUS": 1, "STUB_CONSTRUCT_ONLY": 7}`; invoked directly under production default, two of them wrote to the shared `/tmp`: policy_capability_gate (`/tmp/.nexus/knowledge/policy_memory.jsonl`) and reflex_loop (`/tmp/.nexus/config/reflex_params.json`). The executors and their quoted source lines are preserved on branch `archive/2026-10-13-second-batch`.

| executor key | verdict | kind | gate_passed | what it does | quoted line(s) |
|---|---|---|---|---|---|
| aos_oracle | RETIRING | STUB_CONSTANT_STATUS | None | AosService(repo_root=/tmp).get_status() returns the literal {'status': 'OPERATIONAL', 'aos_version': '145.2', 'trust_score': 0.98, 'governance': 'ACTIVE'} (a... | - |
| attempt_settlement_service | RETIRING | STUB_CONSTRUCT_ONLY | None | constructs AttemptSettlementService with /tmp paths, zero metrics and transaction_mgr={'status': 'simulated'}; rejected as import_construct_not_execution | - |
| battle_swarm | RETIRING | ALIAS | None | delegates to _exec_swarm_multi_agent (same body as the swarm / multi_agent rows); auth-blocked at production default | - |
| decision_formula_engine | RETIRING | STUB_CONSTRUCT_ONLY | None | constructs DecisionFormulaEngine(context=...) and reports class_instantiated; no formula evaluated; rejected as import_construct_not_execution | - |
| dual_loop | RETIRING | STUB_CONSTRUCT_ONLY | None | constructs DualLoopOrchestrator(project_root=/tmp) and reports class_instantiated; rejected as import_construct_not_execution | - |
| entropy_guard_v2 | RETIRING | REAL_CALL | None | EntropyGuardV2().audit_payload(task_desc); outcome keeps only entropy_ok (defaults True) | - |
| learn_refresh_service | RETIRING | STUB_CONSTRUCT_ONLY | None | constructs LearnRefreshService(repo_root=/tmp) and reports class_instantiated; no refresh runs; the registry's construct-only guard then rejects it (import_c... | - |
| mfp_gate | RETIRING | REAL_CALL_CONSTANT_INPUTS | None | evaluate_mfp with constant confidence=0.99, semantic_entropy=0.1, history_success_rate=0.96, so it always returns passed=True (input-independent) | - |
| nightshift_runner_service | RETIRING | AUTH_GATED_REAL_CALL | None | same body as the nightshift row (nightshift aliases it); blocked without NEXUS_LOCAL_MODEL_CALL_ALLOWED / NEXUS_EXTERNAL_RUNTIME_AUTHORIZED; default target R... | - |
| policy_capability_gate | RETIRING | REAL_CALL_FIXTURE_INPUTS | None | calls nexus.services.policy_gate.apply_policy_gate with fixed health metrics and repo_root=/tmp (writes /tmp/.nexus/knowledge/policy_memory.jsonl); returns s... | - |
| predictive_auditor | RETIRING | REAL_CALL_DEGRADED | None | PredictiveAuditor().audit_risk({task_id, constraints}); with no Wisdom Registry table it returns risk_score 0.0 / PROCEED (with a table it would embed locall... | - |
| promotion_engine | RETIRING | STUB_CONSTRUCT_ONLY | None | constructs PromotionEngine() and reports class_instantiated; rejected as import_construct_not_execution | - |
| reflex_loop | RETIRING | REAL_CALL_HARD_CODED_TMP | None | ReflexLoop(project_root=/tmp).run_cycle(): NAS tuner + BattleSwarm tuning against /tmp logs; writes /tmp/.nexus/config/reflex_params.json | - |
| research_and_source_discipline | RETIRING | REAL_CALL_MISUSED_INPUT | None | PythonCodeSkeletonProvider(root=cwd).lookup_implementation(<whole task text>) - the task sentence is looked up as a symbol name | - |
| spec_guarded | RETIRING | REAL_CALL_FIXTURE_INPUTS | None | SpecGuardV2().validate_diagnosis({'task_id'}, constraints) with an empty diagnosis and empty constraints; reports validated (defaults True) | - |
| subagent_outcome_service | RETIRING | STUB_CONSTRUCT_ONLY | None | constructs SubagentOutcomeService(project_root=/tmp) and reports class_instantiated; rejected as import_construct_not_execution | - |
| zero_trust_v2_behavior | RETIRING | STUB_CONSTRUCT_ONLY | None | builds the behavior runner adapter and returns function_called=True (gate passes); the adapter is never run | - |

## REAL_UNATTESTED today

artifact_gate, claim_gate, delivery_gate (postflight invoker) and prompt_compression (runtime-owned compression edge): the effect is real and checked, but the receipt is produced by nexus-runtime, where the Nexus-side attestation (batch 1) does not reach; the runtime producer fix is still needed.

## Wiring-fix backlog (code location that makes each non-real)

| capability | verdict | location and cause |
|---|---|---|
| all receipts | producer cannot attest execution | `nexus_runtime` `CapabilityReceipt.to_dict()` / `build_trace_receipts` never set `claim_boundary.simulated`; fix in nexus-runtime. |
| research, research_route | STUB / BLOCKED | `capability_executor_registry.py:850` (_exec_research) passes `task_statement`; `ResearchPhaseHandler.run` reads `context["task"]`, so output is always "Empty research task.". research_route additionally fails the contract (`missing_outcome_field:control_plane_reference`), is selected on every run and skipped unless triggered. |
| hyper | BLOCKED | `:1245` outcome lacks semantic_status/evidence_refs so the invoker rejects it (`execution_contract_violation`); config fixes candidate_count=1, target README.md, llm_mode=False. |
| nightshift | BLOCKED | `:511/1400` one round, bare task; phase policy denies research (`NightShift Blocked by Phase Policy`), no report written. The directory was right (`<workspace_root>`); the cause was `phase_policy.derive_phase_actions` reading `overall_pass_rate`, a key `PhaseSLOService` never writes, so PassRate was 0% for every real summary (fixed 2026-10-13, `phase_slo_pass_rate`). The fixture workspace has no summary, so it is still denied (`SLO=phase_slo_summary_missing`) before any model call. |
| swarm, multi_agent | BLOCKED | `:1296` only constructs BattleSwarm and calls cleanup; rejected as `import_construct_not_execution`. |
| drone | STUB | `:1341` repair_response_schema/normalize_action on task text; gate passes for any input, no sub-task. |
| ultra_review | REAL (fixed, group D) | was: executor only captured the git diff. Now `UltraReviewService.run(dry_run=False)` in a sandbox worktree (see "Group D fixes"). The earlier product-path block was the audit binding the bounded-implementation worker; the scenario now binds the `independent_review` route's worker, which Admission ALLOWs. |
| autoreason, ddtree | SIMULATED | `:1154` / `:2402` rank/plan one hard-coded candidate c0; BLOCKED_EXTERNAL_AUTH at production default; component probes: Autoreason ranks A>B>C (9/6/3), DDTree prunes 5 to 3 with pruned_count=2. |
| memory | STUB | `:1973` + registry allowlist: `memory_query` never fed, whole task statement used as SQL LIKE pattern. |
| harness_preflight_sensor | STUB | `:2234` pending/selected capabilities are not in the runtime capability context, so the sensor evaluates empty lists and passes vacuously. |
| committee | BLOCKED | canonical context seam forbids keys containing "model" (`committee_proposals[].model`), so proposals cannot reach the executor; controller off without `NEXUS_USE_COMMITTEE`; executor omits `attempt` which the controller indexes. |
| xray | SIMULATED | `:3549` scan target hard-coded to `nexus/services/capability_registry.py`. |
| local_model_executor, repair_loop | BLOCKED | Local stage ran 7 real model calls on the M5 (ledger with Ollama metrics, candidate edit in world-C workspace, source untouched) but `candidate_patch` was empty at the LocalAssistService boundary: `local_output_not_delivered, candidate_not_isolated, verifier_not_passed`; the capability row reports SELECTED_NOT_EXECUTED despite the calls. Not debugged further; may be fixture-specific (world-C copy contained only calc.py). Registry fallback for local_model_executor uses a fixture provider (`capability_registry.py` build_local_model_executor_invoker). |
| codeintel (gap) | REAL_UNATTESTED | executor calls only `lookup_implementation`; graph (4 nodes) and impact set (app/api.py) exist in `graph_builder`/`impact_service` but are not surfaced. |
| mempalace_gate (gap) | REAL_UNATTESTED | blacklist applies to retrieved artifacts, not tool invocations. |
| production policy | gap | planner snapshot defaults `model_call_allowed` to "1" while registry executors require the env var to be set; `nexus run` sets neither. |
| architecture_scout | REAL (fixed, group D) | was: plateau dict lacked `detected`. Remaining gap: `nexus run` feeds no ASI ledger to the node (only the research flow's `HistorySignalStore` has one), so outside the research flow it fails closed `PLATEAU_NOT_DETECTED:insufficient_window`. |
| learn_mode, learn_phase_slo | REAL (fixed 2026-10-13) | was: `_resolve_run_root` gave `<cwd>/.nexus/runtime/<task_id>`, an empty directory. Now `_resolve_learn_store`: `<workspace_root>` (else project_root, else cwd), explicit `run_root` still isolates; phase SLO window 300. Gate is still "report built". |
| swarm_quiet_moment | RETIRING | archived 2026-10-13 (#1906): `_exec_swarm_quiet_moment` returned `build_quiet_moment_event(...)` with no pause enforced or persisted; it now returns the `archived_echo_swarm_quiet_moment_2026-10-13` receipt and `nexus swarm quiet-moment` is removed. |
| registry_sync | BLOCKED (fixed 2026-10-13) | was: `pull_from_peer` returned `[]` on any exception and the executor reported VERIFIED, `peer_contacted=True`. Now `pull_from_peer_checked`: connection error / empty answer / non-ok status -> BLOCKED `REGISTRY_PEER_UNAVAILABLE:<error class>`. |
| jit_validation | SIMULATED | `nexus/core/jit_tool_injector.py:19` `apply_mask` is a keyword mock (Chinese keywords, else first five tools). Since 2026-10-13 the receipt says `simulated=True` / `claim_boundary.claim=SIMULATED`; a real deterministic mask is still owed. |
| file_lock (gap) | REAL | fixed 2026-10-13 (was: lock file keyed by task id, no cross-task exclusion). Remaining: the executor never releases; locks expire after the 1800 s TTL. |
| judge_panel | REAL with local switch (fixed, group D) | Ollama provider added; candidates from the request. Remaining gap: `nexus run` feeds no candidate pool, so the node skips `no_candidate_pool` there. |
| learn_scheduler | REAL (fixed 2026-10-13) | was: `LearnSchedulerService(repo_root=<checkout>)` evaluated the checkout's learning data. Now `project_root=<workspace_root>` -> `learn:phase-policy --project-root`. Remaining: `learn_alert_dispatcher` writes alerts under the cwd. |
| direct_mode, msa_router, research_control_plane, external_doc_scout | NOT_EXECUTABLE (receipt honest since group D) | no physical callable in `PLANNER_EXECUTION_CONTRACTS`; `build_not_executable_invoker` records `NOT_EXECUTABLE:<reason>` (invoked=false, outcome_contributed=false). Giving msa_router an executor is a design task. |
| executor-only keys | RETIRING | archived 2026-10-13 (#1906): the 17 registry entries no planner node reached (8 construct-only, several hard-coding `/tmp` or constant inputs) are removed from `EXECUTOR_REGISTRY`; entropy_guard_v2 gets a real node in #1907 (Nexus-new executor `_exec_entropy_guard_v2` is ready in `PENDING_PLANNER_NODE_EXECUTORS`, not registered until the runtime node exists). |

Not audited: nothing skipped except the RETIRING rows: first batch (federation, oracle_shadow, stress_test, ui_validator, benchmark, learning_closure) and second batch (integration_manager, swarm_quiet_moment, llm_judge_panel, plus the 17 executor-only keys), owned by the archive PRs. Since #1892 every planner node of the pinned runtime has a row.

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


## Group D fixes (2026-10-13, #1981)

Disposition: `DECISION.md` KEEP/FIX items 8 (ultra_review), 9, 10, 11. Partial rerun `--only ultra_review,direct_mode,msa_router,research_control_plane,external_doc_scout,judge_panel,architecture_scout` at 2026-10-13T04:52:33.902428+00:00 (origin/main fe29afcee + this tree, pinned nexus-runtime 2766c15). Model calls only for judge_panel, through the M5 tunnel `127.0.0.1:11434` (qwen3.5:9b); nothing started on this host.

| row | before | after | how |
|---|---|---|---|
| ultra_review | BLOCKED (Workforce: role independent_review), executor STUB | REAL | executor runs `UltraReviewService.run(dry_run=False)` on `workspace_root` in a sandbox git worktree (registration removed afterwards). security_sentry: diff pattern scan + `bandit` + `ruff --select S` on added lines (noise rules B101/B311/B404/B603/B607 and S-equivalents ignored; medium+ blocks). logic_breaker: mirror integrity + `py_compile` + `ruff --select E9,F63,F7,F82` on added lines. ghost_regression: `pytest` on mapped tests (now also `tests/test_<stem>.py` for top-level modules). `executed_checks` lists only what ran; a missing tool fails closed (`check_tool_unavailable`), an empty diff fails closed (`no_diff_to_review`), errors return `status=BLOCKED` with `blocked_reason` instead of raising. Fixture: positive benign diff passes with all 7 checks; negative planted `eval(input())` + broken `handler` fails with `bandit:B307` (ruff S307 corroborating) and `regression_test_failed`. |
| direct_mode, msa_router, research_control_plane | NOT_EXECUTABLE (receipt said BLOCKED_EXECUTOR_UNAVAILABLE / SKIPPED_POLICY_NOT_TRIGGERED) | NOT_EXECUTABLE, receipt `NOT_EXECUTABLE:control_plane_reference` | `capability_registry.NOT_EXECUTABLE_CAPABILITY_REASONS` + `build_not_executable_invoker`: explicit skip, invoked=false, outcome_contributed=false, physical_callable=None, model_calls=0; still selectable. |
| external_doc_scout | NOT_EXECUTABLE (auth gate) | NOT_EXECUTABLE, receipt `NOT_EXECUTABLE:no_live_connector` | same invoker; the auth-gate executor stays in `EXECUTOR_REGISTRY` but the planner node no longer calls it. |
| judge_panel | BLOCKED_EXTERNAL_AUTH:no_judge_provider_configured, one hard-coded candidate c0 | REAL with `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1`; production default BLOCKED_EXTERNAL_AUTH | `OllamaJudgeProvider` (`NEXUS_OLLAMA_URL`, default 127.0.0.1:11434; model from Workforce `routing.local_first.classification`, provider/availability/role checked, no hard-coded model); provider `ollama` in `NEXUS_LLM_JUDGE_PROVIDERS`, or the default when only the local switch is set (local-only authorization never admits gemini/codex command judges). Candidates from `candidate_pool` (`codeintel.judge_panel_candidates`); < 2 distinct candidates fail closed, none -> `no_candidate_pool` skip. Contract predicate `judge_ranked_real_candidates`. One retry on unusable model output. |
| architecture_scout | STUB | REAL | `detect_plateau` (the research flow's detector) over `asi_failure_records` (allowlisted like asi_constraint_extractor); no plateau -> invoked, gate false, `PLATEAU_NOT_DETECTED:<reason>`; contract predicate `architecture_plateau_detected_and_plan_ready`. Not retired: the detector exists. |

Containment (security review follow-up): every lane subprocess (bandit, ruff, py_compile, repro scripts, the pytest re-run) goes through `UltraReviewService._sandboxed_run`: argv list (never a shell), cwd in the sandbox, allowlisted env (PATH/LANG/LC_*/VIRTUAL_ENV, PYTHONPATH without the reviewed checkout; HOME and TMPDIR inside the sandbox; tokens and keys dropped), wall-clock timeout, captured output, and on macOS a `sandbox-exec` profile that denies network, denies reads of credential stores under $HOME and allows writes only to the sandbox worktree. Without that OS barrier (Linux CI) the pytest re-run, the only step that executes PR code, does not run and review mode fails closed (`ghost_regression_not_executed:os_sandbox_unavailable`). Review mode also fails closed when the test lane was skipped by env or had no mapped test, or when a tool timed out. bandit runs with `--ignore-nosec` and ruff with `--isolated --ignore-noqa`, so the diff cannot silence its own findings, and a diff that edits the test harness (conftest.py, pytest.ini, pyproject.toml, ...) gets a `test_harness_modified` finding. Nothing from the diff is imported into the reviewer process.

Also: `nexus ultra-review --no-dry-run` exits 1 on FAIL and 2 on BLOCKED (dry-run stays advisory, gate never passes); `scripts/ops/ultra_gate.py` accepts `mode=review` and requires `status=PASS` for it; a review started from inside a review's own pytest run is refused (`NEXUS_ULTRA_REVIEW_IN_PROGRESS`).

Remaining gaps: `nexus run` feeds neither a candidate pool (judge_panel) nor an ASI ledger (architecture_scout) to the planner nodes; ultra_review reviews `git diff HEAD`, so untracked new files are overlaid into the sandbox but not scanned.
