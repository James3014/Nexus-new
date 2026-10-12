# Capability wiring audit (2026-10)

Issue #1852 (batch 1 fixes: #1862). Original run base: origin/main 929a953d0; current matrix: post-batch-1 on origin/main 4dbac7875 plus #1862. Claim ceiling: `WIRING_AUDIT_EVIDENCE_ONLY` (no benchmark scored, no routing/admission change).

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

## Result matrix (post batch 1, run 2026-10-12T13:19:36.836246+00:00, origin/main 4dbac7875 + #1862)

Verdict counts: `{"BLOCKED": 9, "REAL": 17, "REAL_UNATTESTED": 3, "RETIRING": 6, "STUB": 1}` (was, at 929a953d0: 14 REAL_UNATTESTED, 4 STUB, 3 SIMULATED, 9 BLOCKED, 6 RETIRING, 0 REAL). Receipts are the attested receipts (see "Batch 1 fixes"), which is why `receipt_claims_simulated` is now false for executed rows. `artifact_gate`, `claim_gate`, `delivery_gate` stay REAL_UNATTESTED: their receipts come from the runtime postflight invoker, not the Nexus-side executor receipt, so the Nexus-side attestation does not reach them (runtime producer fix still needed). `research` is BLOCKED_EXTERNAL_AUTH at production default and REAL only with `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1` (see the policy attempts in the `.matrix.json`; the table shows the best verdict). federation, oracle_shadow, stress_test, ui_validator and benchmark are retired at planner level in the pinned runtime (`CapabilityNode.maturity='retired'`; the terminal `_enforce_retired_capabilities` gate forces them `forbidden`), so RETIRING is now the planner's own state, not only an audit annotation; learning_closure is an executor, not a planner node. Full strings are in the `.matrix.json`.

| capability | verdict | executor-level verdict (product path blocked) | production default, selected but untriggered | executor (function @ file:line) | reached via | switches needed | receipt_claims_simulated |
|---|---|---|---|---|---|---|---|
| codeintel | REAL | - | - | _exec_codeintel @ nexus/core/capability_executor_registry.py:733 | EXECUTOR_REGISTRY | none | False |
| research | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_research @ nexus/core/capability_executor_registry.py:851 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| research_route | BLOCKED_execution_contract_violation:missing_outcome_field:control_plane_reference | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_research @ nexus/core/capability_executor_registry.py:851 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| hyper | BLOCKED_semantic_status=FAILED | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_hyper_sprint @ nexus/core/capability_executor_registry.py:1305 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | False |
| nightshift | BLOCKED_semantic_status=BLOCKED(terminal_status=FAILED):console:❌ [NightShift] Blocked by Phase Policy: PassRate=0.0%... | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_nightshift @ nexus/core/capability_executor_registry.py:1504 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| swarm | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1400 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| multi_agent | BLOCKED_EXECUTOR_UNAVAILABLE:import_construct_not_execution | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_swarm_multi_agent @ nexus/core/capability_executor_registry.py:1400 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1; route.escalate_triggered=True | True |
| drone | STUB | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_drone @ nexus/core/capability_executor_registry.py:1445 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| ultra_review | BLOCKED_workforce_admission_blocked: demand_online: Requested role 'independent_review' is outside admitted roles for... | STUB | MISSING | _exec_ultra_review @ nexus/core/capability_executor_registry.py:1804 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| autoreason | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_autoreason @ nexus/core/capability_executor_registry.py:1212 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| ddtree | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_ddtree @ nexus/core/capability_executor_registry.py:2508 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1; route.escalate_triggered=True | False |
| lancedb | REAL | - | - | _exec_lancedb @ nexus/core/capability_executor_registry.py:808 | EXECUTOR_REGISTRY | none | False |
| memory | REAL | - | - | _exec_memory @ nexus/core/capability_executor_registry.py:2077 | EXECUTOR_REGISTRY | none | False |
| mempalace_gate | REAL | - | - | _exec_mempalace @ nexus/core/capability_executor_registry.py:371 | EXECUTOR_REGISTRY | none | False |
| belief | REAL | - | - | _exec_belief @ nexus/core/capability_executor_registry.py:1115 | EXECUTOR_REGISTRY | none | False |
| artifact_gate | REAL_UNATTESTED | - | - | evaluate_postflight_gate @ .venv/lib/python3.14/site-packages/nexus_runtime/support/ser... | POSTFLIGHT_INVOKER | none | True |
| claim_gate | REAL_UNATTESTED | - | - | evaluate_postflight_gate @ .venv/lib/python3.14/site-packages/nexus_runtime/support/ser... | POSTFLIGHT_INVOKER | none | True |
| delivery_gate | REAL_UNATTESTED | - | - | evaluate_postflight_gate @ .venv/lib/python3.14/site-packages/nexus_runtime/support/ser... | POSTFLIGHT_INVOKER | none | True |
| acceptance_check | REAL | - | - | _exec_acceptance_check @ nexus/core/capability_executor_registry.py:2682 | EXECUTOR_REGISTRY | none | False |
| pregate | REAL | - | - | _exec_pregate @ nexus/core/capability_executor_registry.py:2272 | EXECUTOR_REGISTRY | none | False |
| forecast_gate | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_forecast_gate @ nexus/core/capability_executor_registry.py:3422 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| plan_quality_gate | REAL | - | - | _exec_plan_quality_gate @ nexus/core/capability_executor_registry.py:2135 | EXECUTOR_REGISTRY | none | False |
| sandbox | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_sandbox_runner @ nexus/core/capability_executor_registry.py:1513 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| harness_preflight_sensor | REAL | - | - | _exec_harness_preflight_sensor @ nexus/core/capability_executor_registry.py:2340 | EXECUTOR_REGISTRY | none | False |
| committee | BLOCKED_canonical_context_rejected: canonical_context_route_override_forbidden:codeintel.committee_proposals[].model | BLOCKED_semantic_status=FAILED | MISSING | _exec_committee @ nexus/core/capability_executor_registry.py:3232 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | NEXUS_LOCAL_MODEL_CALL_ALLOWED=1,NEXUS_USE_COMMITTEE=1; route.escalate_trigge... | False |
| xray | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_xray @ nexus/core/capability_executor_registry.py:3643 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| metabolism | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_metabolism_resume @ nexus/core/capability_executor_registry.py:1881 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
| meta_opt | REAL | - | SKIPPED_POLICY_NOT_TRIGGERED | _exec_meta_opt @ nexus/core/capability_executor_registry.py:3864 | EXECUTOR_REGISTRY via build_escalate_gated_invoker | none; route.escalate_triggered=True | False |
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
| codeintel | invoked_with_evidence_and_artifact_assertions_passed |  |
| research | invoked_with_evidence_and_artifact_assertions_passed |  |
| research_route | executor_or_runtime_blocked |  |
| hyper | executor_or_runtime_blocked | failed: sprint_status_success |
| nightshift | executor_or_runtime_blocked | failed: recovery_report_written, terminal_success |
| swarm | executor_or_runtime_blocked | failed: swarm_executed_workers, no_construct_only_rejection |
| multi_agent | executor_or_runtime_blocked | failed: swarm_executed_workers, no_construct_only_rejection |
| drone | outcome_independent_of_fixture_input | failed: subtask_artifact_written, action_normalized_from_task, negative_control:different_task_gives_different_result |
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


## Batch 1 fixes

Issue #1862 (stacks on #1861). Seven rows re-run with the same switches as the main audit (`uv run --extra legacy python scripts/ops/capability_wiring_audit.py --only research,memory,autoreason,ddtree,hyper,xray,harness_preflight_sensor`; M5 tunnel `127.0.0.1:11434`, model `qwen2.5-coder:7b-instruct`, nothing started locally). Before: run `2026-10-12T08:40:11.324859+00:00` on origin/main 1324a1e1e. After: run `2026-10-12T11:20:15.817191+00:00` on this branch. Verdict counts before `{"BLOCKED": 1, "SIMULATED": 3, "STUB": 3}`, after `{"BLOCKED": 1, "REAL": 6}`.

The audit scenarios now supply the request inputs the fixed executors read (`codeintel.autoreason_candidates`, `ddtree_candidates`, `xray_targets`, `hyper_*`, `memory_query`), because the executors no longer invent them. Unit tests: `tests/services/test_capability_wiring_fixes_batch1.py`.

| capability | before | after | receipt simulated before -> after | note |
|---|---|---|---|---|
| research | STUB | production default: BLOCKED_EXTERNAL_AUTH; with `NEXUS_EXTERNAL_RUNTIME_AUTHORIZED=1`: REAL | True -> False | executor passes `task` (handler key) plus `task_statement`; per-task run dir `.nexus/research/<task_id>` (was shared `/tmp`, whose `researchpack.json` cache returned one task's pack for all); gate fails on empty task or provider `status=FAIL`. Provider egress (chub CLI / felo) is blocked unless the env switch is set (`provider_call_count=0`); URLs in the task are stripped and never fetched; the `~/.openclaw` LanceDB cache is disabled for this executor. |
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
