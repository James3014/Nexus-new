# Capability wiring audit (2026-10)

Issue #1852. Base: origin/main 929a953d0. Claim ceiling: `WIRING_AUDIT_EVIDENCE_ONLY` (no benchmark scored, no routing/admission change).

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

## Verdicts

- `REAL_UNATTESTED`: the executor ran, evidence refs exist and the artifact assertion passed, but the receipt still says `claim_boundary.simulated=true`. `REAL` is reserved for the same case with `simulated=false`, which never occurs.
- `SIMULATED`: executor runs but its inputs are hard-coded or fixture-provided. `STUB`: constant outcome, input-independent outcome, or gate passes without any checkable effect. `BLOCKED_<exact reason>`, `NOT_SELECTABLE`, `RETIRING`, `MODEL_UNAVAILABLE` as specified.
- `claim_boundary.simulated` is recorded in column `receipt_claims_simulated` and is **not** an execution signal: `CapabilityReceipt.to_dict()` emits `claim_boundary` without `simulated`, `ClaimBoundary` defaults it to true, and nothing in nexus-runtime or Nexus-new sets it false for capability receipts. All 29 executed rows say true.

## Result matrix (verbatim, run 20261012T080857Z on 929a953d0)

Verdict counts: `{json.dumps(m["verdict_counts"])}`. Full (untruncated) reason strings are in the JSON.

| capability | verdict | executor-level verdict (product path blocked) | production default, selected but untriggered | executor (function @ file:line) | reached via | switches needed | receipt_claims_simulated |
|---|---|---|---|---|---|---|---|
| codeintel | REAL_UNATTESTED | - | - | _exec_codeintel @ nexus/core/capability_executor_registry.py:732 | EXECUTOR_REGISTRY | none | True |
| research | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_research @ nexus/core/capability_executor_registry.py:850 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| research_route | BLOCKED_execution_contract_violation:missing_outcome_field:control_plane_reference | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_research @ nexus/core/capability_executor_registry.py:850 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| hyper | BLOCKED_execution_contract_violation:missing_evidence_field:evidence_refs,missing_outcome_field:evidence_refs,missing... | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_hyper_sprint @ nexus/core/capability_executor_registry.py:1245 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| nightshift | BLOCKED_semantic_status=BLOCKED(terminal_status=FAILED):console:❌ [NightShift] Blocked by Phase Policy: PassRate=0.0%... | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_nightshift @ nexus/core/capability_executor_registry.py:1400 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| swarm | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1296 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| multi_agent | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1296 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| drone | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_drone @ nexus/core/capability_executor_registry.py:1341 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| ultra_review | BLOCKED_workforce_admission_blocked: demand_online: Requested role 'independent_review' is outside admitted roles for... | STUB | MISSING | _exec_ultra_review @ nexus/core/capability_executor_registry.py:1700 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| autoreason | SIMULATED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_autoreason @ nexus/core/capability_executor_registry.py:1154 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | True |
| ddtree | SIMULATED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_ddtree @ nexus/core/capability_executor_registry.py:2402 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | True |
| lancedb | REAL_UNATTESTED | - | - | _exec_lancedb @ nexus/core/capability_executor_registry.py:807 | EXECUTOR_REGISTRY | none | True |
| memory | STUB | - | - | _exec_memory @ nexus/core/capability_executor_registry.py:1973 | EXECUTOR_REGISTRY | none | True |
| mempalace_gate | REAL_UNATTESTED | - | - | _exec_mempalace @ nexus/core/capability_executor_registry.py:370 | EXECUTOR_REGISTRY | none | True |
| belief | REAL_UNATTESTED | - | - | _exec_belief @ nexus/core/capability_executor_registry.py:1057 | EXECUTOR_REGISTRY | none | True |
| artifact_gate | REAL_UNATTESTED | - | - | evaluate_postflight_gate @ nexus_runtime/support/services/online_nexus_context.py:858 | POSTFLIGHT_INVOKER | none | True |
| claim_gate | REAL_UNATTESTED | - | - | evaluate_postflight_gate @ nexus_runtime/support/services/online_nexus_context.py:858 | POSTFLIGHT_INVOKER | none | True |
| delivery_gate | REAL_UNATTESTED | - | - | evaluate_postflight_gate @ nexus_runtime/support/services/online_nexus_context.py:858 | POSTFLIGHT_INVOKER | none | True |
| acceptance_check | REAL_UNATTESTED | - | - | _exec_acceptance_check @ nexus/core/capability_executor_registry.py:2576 | EXECUTOR_REGISTRY | none | True |
| pregate | REAL_UNATTESTED | - | - | _exec_pregate @ nexus/core/capability_executor_registry.py:2166 | EXECUTOR_REGISTRY | none | True |
| forecast_gate | REAL_UNATTESTED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_forecast_gate @ nexus/core/capability_executor_registry.py:3316 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| plan_quality_gate | REAL_UNATTESTED | - | - | _exec_plan_quality_gate @ nexus/core/capability_executor_registry.py:2029 | EXECUTOR_REGISTRY | none | True |
| sandbox | REAL_UNATTESTED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_sandbox_runner @ nexus/core/capability_executor_registry.py:1409 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| harness_preflight_sensor | STUB | - | - | _exec_harness_preflight_sensor @ nexus/core/capability_executor_registry.py:2234 | EXECUTOR_REGISTRY | none | True |
| committee | BLOCKED_canonical_context_rejected: canonical_context_route_override_forbidden:codeintel.committee_proposals[].model | BLOCKED_semantic_status=FAILED | MISSING | _exec_committee @ nexus/core/capability_executor_registry.py:3126 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1,NEXUS_USE_COMMITTEE=1; route.escalate_trigge... | True |
| xray | SIMULATED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_xray @ nexus/core/capability_executor_registry.py:3537 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| metabolism | REAL_UNATTESTED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_metabolism_resume @ nexus/core/capability_executor_registry.py:1777 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| meta_opt | REAL_UNATTESTED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_meta_opt @ nexus/core/capability_executor_registry.py:3748 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | True |
| local_model_executor | BLOCKED_SELECTED_NOT_EXECUTED:planner_selected_no_runtime_executor:local_stage[local_output_not_delivered,candidate_n... | - | - | LocalModelExecutor.run @ nexus/services/local_heal/local_model_executor.py:1065 | LOCAL_STAGE | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 | True |
| repair_loop | BLOCKED_local_model_executor_not_proven,missing_candidate_hash,candidate_hash_not_applied,verifier_not_passed,local_r... | - | - | LocalModelExecutor.run @ nexus/services/local_heal/local_model_executor.py:1065 | LOCAL_STAGE | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1 | True |
| federation | RETIRING | - | - | - | - | none | None |
| oracle_shadow | RETIRING | - | - | - | - | none | None |
| stress_test | RETIRING | - | - | - | - | none | None |
| ui_validator | RETIRING | - | - | - | - | none | None |
| benchmark | RETIRING | - | - | - | - | none | None |
| learning_closure | RETIRING | - | - | - | - | none | None |

| capability | verdict reason | failed assertions / notes |
|---|---|---|
| codeintel | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| research | outcome_independent_of_fixture_input | failed: task_text_reached_handler, findings_reference_the_question, negative_control:different_question_gives_different_result |
| research_route | executor_or_runtime_blocked | failed: task_text_reached_handler, findings_reference_the_question, negative_control:different_question_gives_different_result |
| hyper | executor_or_runtime_blocked | failed: sprint_status_success, sprint_produced_at_least_two_candidates |
| nightshift | executor_or_runtime_blocked | failed: recovery_report_written, terminal_success |
| swarm | executor_or_runtime_blocked | failed: swarm_executed_workers, no_construct_only_rejection |
| multi_agent | executor_or_runtime_blocked | failed: swarm_executed_workers, no_construct_only_rejection |
| drone | outcome_independent_of_fixture_input | failed: subtask_artifact_written, action_normalized_from_task, negative_control:different_task_gives_different_result |
| ultra_review | capability_never_invoked | failed: planted_eval_input_flagged |
| autoreason | executor_uses_hard_coded_inputs:"id": "c0"@nexus/core/capability_executor_registry.py:1179 | failed: ranked_three_seeded_candidates, scores_not_constant |
| ddtree | executor_uses_hard_coded_inputs:"candidate_id": "c0"@nexus/core/capability_executor_registry.py:2426 | failed: pruned_five_candidate_pool, recorded_pruned_count_ge_2 |
| lancedb | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| memory | outcome_independent_of_fixture_input | failed: seeded_insight_retrieved, negative_control:unrelated_query_has_no_hits |
| mempalace_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| belief | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| artifact_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| claim_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| delivery_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| acceptance_check | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| pregate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| forecast_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| plan_quality_gate | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| sandbox | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| harness_preflight_sensor | gate_passed_without_checkable_effect:sensor_saw_planned_selection | failed: sensor_saw_planned_selection |
| committee | capability_never_invoked | failed: verdicts_recorded, winner_or_abstain, negative_control:single_candidate_blocks |
| xray | executor_uses_hard_coded_inputs:"nexus/services/capability_registry.py"@nexus/core/capability_executor_registry.py:3549 |  |
| metabolism | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| meta_opt | executor_ran_and_artifact_passed_but_receipt_claims_simulated_true |  |
| local_model_executor | executor_or_runtime_blocked | failed: candidate_delivered_to_runtime |
| repair_loop | executor_or_runtime_blocked | failed: candidate_delivered_to_runtime, verifier_passed_on_candidate |
| federation | federation (archive PR) |  |
| oracle_shadow | aos_oracle / oracle promote (archive PR) |  |
| stress_test | stress_test + _exec_stress_test (archive PR) |  |
| ui_validator | ui_explorer / ui-validator + _exec_ui_validator (archive PR) |  |
| benchmark | benchmark_service + _exec_benchmark (archive PR) |  |
| learning_closure | _exec_learning_closure (archive PR; executor only, not a planner node) |  |


## REAL_UNATTESTED today (eligible for re-measurement)

codeintel (symbol lookup only), lancedb, mempalace_gate (blacklist blocks a tagged artifact), belief (read of seeded failure: 0.1 vs 0.7 default), artifact_gate, claim_gate, delivery_gate, acceptance_check, pregate, forecast_gate, plan_quality_gate, sandbox (isolated copy, stdout recorded), metabolism, meta_opt. Escalate-gated ones (forecast_gate, sandbox, metabolism, meta_opt) only run when `escalate_triggered` is set; in production default they are selected and skipped.

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

Not audited: nothing skipped except the RETIRING rows (federation, oracle_shadow, stress_test, ui_validator, benchmark, learning_closure), owned by the archive PR.

## capability_route_smoke.py

- On this host the smoke first failed closed with exit 78 (`LEGACY_EXTRA_REQUIRED`: bench subprocess used `uv run` without the legacy extra). Re-run with `NEXUS_BENCH_SUBPROCESS_PYTHON` set: **fails** (`passed: false`; route_oracles 8/8 rows fail with `evidence_without_gate_pass` / `selected_without_invocation` / `missing_verifier_artifact;missing_source_hash`; 14 of 15 task rows fail overall).
- It does **not** read `simulated`: its validators (and `capability_receipt_policy.py`, `gemini_nexus_report.py`) contain zero references. A synthetic with-Nexus row whose receipts all carry `claim_boundary.simulated=true` passes the row validator with no failures (`audit.smoke_probe`, covered by a test). So it fails here for gate/evidence reasons, but would pass on simulated receipts that look successful.
