---
aliases: '[Governance Log, Audit Log, System [Evolution
  Log](../07_Diffs/Diff - v17.1 vs v22 vs v23.md)]'
confidence: high
last_compiled: '2026-04-06'
owner: agent
related_pages: ''
source_of_truth: MUSE-NEXUS-Engine-Specification-v22-Eternal.md
status: active
tags: '[ops, [[CHANGELOG|changelog]], governance, evolution]'
title: Ops - Governance [[CHANGELOG|Changelog]]
type: ops
version_scope: '[v17.1, v22, v23]'
---

# Ops - Governance [[CHANGELOG]]

## 2026-04-16
- **Perf (Learn):** Improved citation precision with relevance reranking and strict unknown gate. Added precision benchmark suite.

## 2026-04-16
- **Perf (Resilience):** Unified timeout and retry policy across Hyper/NightShift. Reduced `infra_blocked_rate` and optimized pytest overhead.

## 2026-04-23
- **Trust + Routing Hardening:** Unified semantic completion contract for `learn:*` work commands and added fixed guard audit for `research:auto-flow` hard-task routing (`tests/engine/test_research_auto_flow_guard_audit.py`) to prevent false baseline demotion regressions.

## 2026-04-23
- **Capability Wave 6~12 (Minimal Operational Baseline):** Added phase KPI dashboard command (`learn:phase-kpi`), auto prior-fix retrieval weighting in route decision, belief-driven hyper budget tuning, nightshift recommendation signalization, drone crystal semantic contract fields, and autotune script (`scripts/bench/capability_autotune.py`) with backup-on-apply.

## 2026-05-20
- **HEEP MAT-B Verification-Only Manifest Repair:** Updated the Flash+Nexus compare task manifest builder so internal HEEP MAT-B compare tasks use the runner-native `all_target_tests_pass` criterion while receipt-chain completeness remains judged by the MAT-B report layer. This keeps verification-only rows from being misclassified as artifact-change delivery tasks and preserves fail-closed receipt/token gates.

## 2026-05-20
- **HEEP MAT-B Blocked Mode Resolution:** Added a fail-closed resolver that separates internal non-cost mode selection from provider-token/public eligibility for blocked MAT-B rows. Provider-token blockers can record stronger non-cost multi-skill evidence without unlocking runtime defaults, while executor receipt blockers remain undecided until expected capability receipts exist.

## 2026-05-20
- **HEEP MAT-B Final Skill Decisions:** Added a final blocked-capability skill decision packet that assigns a usable skill or skill set to all 13 blocked capabilities. Provider-token blockers select multi-skill for internal non-cost use; executor receipt blockers select single primary fallback until receipt replay proves the multi-skill challenger.

## 2026-05-20
- **HEEP Executor Receipt Route Smoke:** Ran deterministic route receipt smoke and recorded public-safe `drone`, `nightshift`, and `swarm` receipts. Final HEEP skill decisions now distinguish route-level executor receipt readiness from the remaining skill-specific MAT-B/provider-clean replay gates.

## 2026-05-21
- **Zero-Trust V2 Skill Promotion Baseline:** Added a separate V2 promotion control plane for skill replacement review. Current runtime overlay remains `v1_diagnostic_only`; V2 artifacts now produce curation backlog, replay matrix, promotion report, and manual apply plan with `runtime_mutation_allowed=false`, `automatic_apply_allowed=false`, and `public_benchmark_allowed=false` until runtime-signed receipts, approved sandbox attestation, clean-slate baseline sandwich, negative-control blocking, and manual operator acknowledgement all pass.
- **Zero-Trust V2 Physical Sandbox Probe:** Added a macOS `sandbox-exec` probe and V2 physical row wrapper that emits runner-owned sandbox attestation, runtime-signed receipt shape, clean-slate sandwich, and negative-control accounting. The wrapper defaults to `probe_only=true` / `promotion_credit_allowed=false`, so sandbox probes cannot promote skill replacements without true skill execution evidence.
- **Zero-Trust V2 M1-M6 Rollout Reports:** Added P0 command specs, physical skill evidence, evidence accumulation, unification plan, and 34-capability rollout status. Current result is intentionally blocked for runtime unification: only one P0 skill asset was command-ready, the evidence is `materialization_only=true`, `ready_for_manual_apply_count=0`, and all 34 capabilities remain on V1/current runtime path until real skill behavior evidence exists.
- **Zero-Trust V2 M7-M12 Final Verdict:** Added behavior evidence extraction, behavior promotion report, manual trial, P0 rollout, and M12 34-capability final verdict. M12-3 is complete as a verdict pass: 19 candidate capabilities are structured-blocked for missing V2 behavior evidence, 15 capabilities have no V2-ready candidate, and runtime mutation remains locked.

## One-sentence summary
記錄 Nexus 治理架構的所有重大變更、審計硬化與契約遷移歷史。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- 維護治理變更記錄，保證技術決策與風險緩解可追溯。 [Source: scripts/ops/ci_gate.py]

## Upstream
- `05_Protocols/Protocol - Evidence Map.md`：治理協定輸入來源。 [Source: 05_Protocols/Protocol - Evidence Map.md]

## Downstream
- 供 `06_Ops/Ops - Closeout Hard Gate.md` 與發佈門禁參考。 [Source: 06_Ops/Ops - Closeout Hard Gate.md]
- 供 `06_Ops/Ops - Acceptance and Release.md` 作為歷史背景。 [Source: 06_Ops/Ops - Acceptance and Release.md]

## Related modules / files
- `scripts/ops/ci_gate.py`: governance 變更驗證入口。 [Source: scripts/ops/ci_gate.py]
- `03_Flows/Flow - PXDRAC Runtime.md`: 運行策略參考。 [Source: 03_Flows/Flow - PXDRAC Runtime.md]

## Source notes
- 變更歷史依據來自實際腳本審計紀錄與 CI 驗證。 [Source: scripts/ops/ci_gate.py]

## Open questions / conflicts
- [ ] 是否新增「失效/回滾」欄位標準化輸出。 [Source: scripts/ops/ci_gate.py]

## Role / responsibility
- **歷史溯源**: 提供系統治理邏輯演化的完整 Traceability。 [Source: scripts/ops/ci_gate.py]
- **風險管理**: 記錄每次變更的風險等級與回滾計畫，確保治理硬化的穩定性。

---

[[System Overview]]

## Governance Change History (治理變更歷史)

| Date | Change (項) | Affected Components | Risk | Rollback Plan | Verifier |
|---|---|---|---|---|---|
| 2026-05-21 | **Zero-Trust V2 M7-M12 Final Verdict: behavior evidence extraction through 34-capability verdict completion** | `nexus/learning/zero_trust_v2_behavior.py`, `scripts/ops/build_zero_trust_v2_behavior_evidence.py`, `scripts/ops/build_zero_trust_v2_behavior_promotion_report.py`, `scripts/ops/build_zero_trust_v2_manual_trial.py`, `scripts/ops/build_zero_trust_v2_p0_rollout.py`, `scripts/ops/build_zero_trust_v2_final_rollout_completion.py`, `tests/` | Medium | Git revert; keep V1 runtime overlay active | Codex |
| 2026-05-21 | **Zero-Trust V2 M1-M6 Rollout Reports: command specs through 34-capability unification status** | `nexus/learning/zero_trust_v2_skill_gate.py`, `scripts/ops/build_zero_trust_v2_skill_command_specs.py`, `scripts/ops/build_zero_trust_v2_physical_skill_evidence.py`, `scripts/ops/build_zero_trust_v2_evidence_accumulation.py`, `scripts/ops/build_zero_trust_v2_unification_plan.py`, `scripts/ops/build_zero_trust_v2_rollout_status.py`, `tests/` | Medium | Git revert; keep V1 runtime overlay active | Codex |
| 2026-05-21 | **Zero-Trust V2 Physical Sandbox Probe: runner-owned macOS attestation with probe-only promotion boundary** | `nexus/learning/zero_trust_v2_physical_sandbox.py`, `nexus/learning/zero_trust_v2_physical_runner.py`, `scripts/ops/build_zero_trust_v2_sandbox_probe.py`, `scripts/ops/run_zero_trust_v2_physical_sandbox.py`, `tests/learning/test_zero_trust_v2_physical_*`, `tests/ops/test_run_zero_trust_v2_physical_sandbox.py`, `docs/reports/NEXUS_ZERO_TRUST_V2_*SANDBOX*` | Medium | Git revert; keep probe-only default | Codex |
| 2026-05-21 | **Zero-Trust V2 Skill Promotion Baseline: v1 diagnostic overlay separated from v2-only promotion control plane** | `nexus/learning/zero_trust_v2_*`, `scripts/ops/build_zero_trust_v2_*`, `tests/learning/test_zero_trust_v2_*`, `tests/ops/test_build_zero_trust_v2_*`, `docs/reports/NEXUS_ZERO_TRUST_V2_*`, `docs/plans/NEXUS_ZERO_TRUST_V2_PROMOTION_IMPLEMENTATION_PLAN_2026-05-21.md` | Medium | Git revert; keep existing runtime overlay A path | Codex |
| 2026-05-20 | **HEEP MAT-B Receipt Executor Repair: explicit blocker queue and swarm bench executor env for drone/nightshift/swarm rows** | `scripts/ops/build_heep_mat_b_blocker_resolution_queue.py`, `scripts/ops/build_heep_flash_nexus_compare_matrix.py`, `docs/reports/NEXUS_HEEP_MAT_B_BLOCKER_RESOLUTION_QUEUE_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md`, `tests/ops/` | Medium | Git revert | Codex |
| 2026-05-20 | **Routing Spec V2 Closure: RLM handoff receipt, OutcomeMemory trust-clean soak, dispatcher plan consume, mutation assurance read-model gate** | `nexus/engine/rlm_controller.py`, `nexus/app/research_flow_service.py`, `nexus/learning/outcome_memory.py`, `nexus/engine/route_runtime_dispatcher.py`, `scripts/ops/build_claim_evidence_read_model.py`, `tests/` | Medium | Git revert | Codex |
| 2026-05-20 | **RLM Bounded Orchestration Adapter: X/R-loop receipts without recursive dispatch or public/runtime unlock** | `nexus/engine/rlm_controller.py`, `nexus/app/research_flow_service.py`, `nexus/contracts/routing_spec_v2_backlog.py`, `tests/engine/test_rlm_outcome_integration.py`, `tests/contracts/test_routing_spec_v2_backlog.py`, `docs/plans/` | Medium | Git revert | Codex |
| 2026-05-20 | **Full CI Eval Policy Semantics: percent-style threshold normalization and warn-only eval gate behavior** | `nexus/core/gate_evaluator.py`, `scripts/ops/ci_gate.py`, `tests/core/test_gate_evaluator_policy.py`, `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md` | Medium | Git revert | Codex |
| 2026-05-20 | **Full CI Wiki Governance Scope: legacy/report/archive soft-contract classification for full gate pass** | `scripts/ops/wiki_linter.py`, `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md`, `nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md` | Medium | Git revert | Codex |
| 2026-05-20 | **Full CI Transient Artifact Cleanup: restore known tracked generated outputs on success** | `scripts/ops/ci_gate.py`, `tests/ops/test_ci_gate_closeout_contract.py`, `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md`, `nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md` | Low | Git revert | Codex |
| 2026-05-20 | **Non-Swarm/NSP Refactor Closure: CompletionEnvelope read-model validation and evidence union-merge guard** | `nexus/contracts/claim_evidence_read_model.py`, `nexus/contracts/evidence_retention.py`, `scripts/ops/build_claim_evidence_read_model.py`, `tests/contracts/`, `tests/ops/`, `tests/core/`, `docs/plans/` | Low | Git revert | Codex |
| 2026-05-20 | **Routing Refactor Boundary Gates: Context adapter fail-closed, AutonomicRouter-forward DAG serialization, routing spec v2 forbidden-path backlog gate** | `nexus/core/context_runtime_adapter.py`, `nexus/contracts/route_dag_pregate.py`, `nexus/contracts/routing_spec_v2_backlog.py`, `tests/contracts/`, `tests/core/`, `docs/reports/`, `docs/plans/` | Medium | Git revert | Codex |
| 2026-05-20 | **HEEP MAT-B Closure Packets: executor-trio replay blocker, rollup V2, mode gate V2, runtime review V2, public/taskcard gates** | `scripts/ops/build_heep_mat_b_closure_packets.py`, `tests/ops/test_build_heep_mat_b_closure_packets.py`, `docs/reports/NEXUS_HEEP_MAT_B_*`, `docs/reports/NEXUS_HEEP_MODE_MAP_UPDATE_GATE_V2_2026-05-20.json`, `docs/reports/NEXUS_HEEP_RUNTIME_APPLY_REVIEW_PACKET_V2_2026-05-20.json`, `docs/reports/NEXUS_HEEP_PUBLIC_BENCHMARK_READINESS_GATE_2026-05-20.json`, `docs/reports/NEXUS_HEEP_TASKCARD_STATUS_R1_R6_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md` | Low | Git revert | Codex |
| 2026-05-20 | **HEEP Provider/Receipt RCA: classify token truth as provider-clean replay blocker and receipt miss as downstream model-delivery blocker** | `scripts/ops/build_heep_mat_b_closure_packets.py`, `tests/ops/test_build_heep_mat_b_closure_packets.py`, `docs/reports/NEXUS_HEEP_PROVIDER_RECEIPT_BLOCKER_RCA_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md` | Low | Git revert | Codex |
| 2026-05-20 | **HEEP Executor Trio Next-Step Gate: local receipt readiness passes, provider-clean MAT-B replay remains the only admissible blocker** | `scripts/ops/build_heep_mat_b_closure_packets.py`, `tests/ops/test_build_heep_mat_b_closure_packets.py`, `docs/reports/NEXUS_HEEP_EXECUTOR_TRIO_NEXT_STEP_PACKET_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md` | Low | Git revert | Codex |
| 2026-05-20 | **HEEP Provider-Clean Replay Attempt: executor trio still blocked by provider token truth, not skill readiness** | `docs/reports/NEXUS_HEEP_EXECUTOR_TRIO_PROVIDER_CLEAN_REPLAY_STATUS_2026-05-20.json`, `docs/reports/NEXUS_HEEP_PROVIDER_CLEAN_REPLAY_RCA_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md` | Low | Git revert | Codex |
| 2026-05-20 | **SFV2 Skill Selection Pipeline: source tier, single/multi decision, role-ablation matrix, catalog/update/review states for 34 capabilities** | `scripts/ops/build_sfv2_skill_selection_pipeline.py`, `tests/ops/test_build_sfv2_skill_selection_pipeline.py`, `docs/reports/NEXUS_SFV2_SKILL_SELECTION_PIPELINE_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md`, `docs/plans/NEXUS_EMAS_EVOLUTION_PLAN.md`, `docs/info/NEXUS_CAPABILITY_SKILL_MAP.md` | Low | Git revert | Codex |
| 2026-05-20 | **SFV2 Role-Ablation Probe: 9 approved multi-skill assemblies expanded into 29 full/minus-role replay arms** | `scripts/ops/build_sfv2_role_ablation_probe.py`, `tests/ops/test_build_sfv2_role_ablation_probe.py`, `docs/reports/NEXUS_SFV2_ROLE_ABLATION_PROBE_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md`, `docs/plans/NEXUS_EMAS_EVOLUTION_PLAN.md` | Low | Git revert | Codex |
| 2026-05-20 | **SFV2 Role-Ablation Execution: runner-ready 29-row matrix plus full live replay rollup, 29/29 PASS, runtime/public still locked** | `scripts/ops/build_sfv2_role_ablation_matrix.py`, `tests/ops/test_build_sfv2_role_ablation_matrix.py`, `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EXECUTION_MATRIX_2026-05-20.json`, `docs/reports/NEXUS_SFV2_ROLE_ABLATION_LIVE_ROLLUP_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md`, `docs/plans/NEXUS_EMAS_EVOLUTION_PLAN.md` | Low | Git revert | Codex |
| 2026-05-21 | **SFV2 Role-Ablation Edgecase Replay: 20 role-focused tasks, 40/40 live rows PASS, role requiredness still not proven** | `scripts/ops/build_sfv2_role_ablation_edgecase_matrix.py`, `tests/ops/test_build_sfv2_role_ablation_edgecase_matrix.py`, `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_EXECUTION_MATRIX_2026-05-21.json`, `docs/reports/NEXUS_SFV2_ROLE_ABLATION_EDGECASE_LIVE_ROLLUP_2026-05-21.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md`, `docs/plans/NEXUS_EMAS_EVOLUTION_PLAN.md` | Low | Git revert | Codex |
| 2026-05-21 | **SFV2 Role-Requiredness Assertions: machine-checkable role necessity packet over edgecase replay, 0/20 requiredness proven** | `scripts/ops/build_sfv2_role_requiredness_assertions.py`, `tests/ops/test_build_sfv2_role_requiredness_assertions.py`, `docs/reports/NEXUS_SFV2_ROLE_REQUIREDNESS_ASSERTION_PACKET_2026-05-21.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md`, `docs/plans/NEXUS_EMAS_EVOLUTION_PLAN.md` | Low | Git revert | Codex |
| 2026-04-23 | **Capability Insight Patch: Parse-typed tuning knobs + route-consensus observability wired into ops loop/trend gate/ci summary** | `nexus/app/research_flow_service.py`, `scripts/bench/capability_ab_runner.py`, `scripts/bench/capability_ops_loop.py`, `scripts/ops/ci_gate.py`, `tests/app/test_research_flow_service.py`, `tests/benchmark/test_capability_ab_runner.py`, `tests/benchmark/test_capability_ops_loop.py` | Low | Git revert | Codex |
| 2026-04-23 | **Capability Max Wave (6/6): speed-first flow ladder, cross-module risk routing, token-estimation fallback, 12-task xmod probes, 3-round median trend gate** | `nexus/app/research_flow_service.py`, `nexus/research/sprint_service.py`, `scripts/bench/capability_ops_loop.py`, `scripts/bench/capability_tasks_cross_module_v1.json`, `scripts/ops/ci_gate.py`, `tests/app/test_research_flow_service.py`, `tests/research/test_sprint_service.py`, `tests/benchmark/*` | Medium | Git revert | Codex |
| 2026-04-23 | **Capability Trust/Execution Wave: Profile-Aware Tuning Routing + Token Semantic Status + CI Health Surfacing** | `nexus/research/sprint_service.py`, `nexus/app/research_flow_service.py`, `scripts/bench/capability_ab_runner.py`, `scripts/bench/capability_autotune.py`, `scripts/bench/capability_ops_loop.py`, `scripts/ops/ci_gate.py`, `tests/benchmark/*`, `tests/research/test_local_mutator_safety.py`, `tests/engine/test_research_auto_flow_guard_audit.py`, `tests/app/test_research_flow_service.py` | Medium | Git revert | Codex |
| 2026-04-23 | **Capability Wave Extension: Dual-Objective Autotune + Health Score + LLM Probe Telemetry** | `scripts/bench/capability_autotune.py`, `scripts/bench/capability_ops_loop.py`, `tests/benchmark/test_capability_autotune.py`, `tests/benchmark/test_capability_ops_loop.py` | Medium | Git revert | Codex |
| 2026-04-23 | **Capability Optimization Wave: Median Autotune Hysteresis + Hard First-Pass Lift + Token Measurement Visibility** | `scripts/bench/capability_autotune.py`, `scripts/bench/capability_ab_runner.py`, `scripts/bench/capability_ops_loop.py`, `scripts/bench/ab_eval.py`, `nexus/app/research_flow_service.py`, `nexus/research/local_sprint_mutator.py`, `tests/benchmark/*`, `tests/research/test_local_mutator_safety.py`, `tests/engine/test_research_auto_flow_guard_audit.py` | Medium | Git revert | Codex |
| 2026-04-23 | **Capability Upgrade: Token Observability + Baseline Probe Reuse + Hard First-Pass Guardrails** | `nexus/research/sprint_service.py`, `nexus/app/research_flow_service.py`, `nexus/research/local_sprint_mutator.py`, `scripts/bench/ab_eval.py`, `scripts/bench/capability_ab_runner.py`, `scripts/bench/capability_autotune.py`, `tests/research/`, `tests/engine/test_research_auto_flow_guard_audit.py`, `tests/benchmark/` | Medium | Git revert | Codex |
| 2026-04-20 | **TELEMETRY PURIFICATION & ASYNC IO EVOLUTION** | `commander.py`, `context_hub.py`, `msa_indexer.py`, `campaign_general.py` | High | Git revert | Antigravity |
| 2026-04-20 | **UNIFIED SERVICE REGISTRY** | `nexus/services/registry.py`, `services/__init__.py` | Medium | Git revert | Antigravity |
|---|---|---|---|---|---|
| 2026-04-20 | **IO HARDENING & STATE PRUNING** | `state_repository.py`, `msa_indexer.py`, `event_bus.py` | High | Git revert | Antigravity |
| 2026-04-20 | **CORE DEBT DISCOVERY (STAGE 7)** | `commander.py`, `context_hub.py`, `crystal.py` | Medium | Git revert | Gemini-Nexus |
|---|---|---|---|---|---|
| 2026-04-20 | **GOVERNANCE OPTIMIZATION & COGNITION HARDENING** | `vector_rag.py`, `ci_gate.py`, `nexus_swarm_sse.py` | High | Git revert | Antigravity |
| 2026-04-20 | **QUALITY UNIFICATION & TEST RESTRUCTURING** | `pytest.ini`, `tests/` | Medium | Git revert | Antigravity |
|---|---|---|---|---|---|
| 2026-04-20 | **DEEP PURIFICATION (STAGE 4)** | `context_hub.py`, `swarm.py`, `campaign_general.py` | High | Git revert | Gemini-Nexus |
| 2026-04-20 | **STRUCTURAL DEBT PURGE** | `router.py`, `self_evolve_engine.py`, `onebit_core.py` | High | Git revert | Antigravity |
| 2026-04-20 | **DEEP DEBT AUDIT & REALIGNMENT** | Brain Hub, `router.py`, `self_evolve_engine.py` | High | Git revert | Gemini-Nexus |
| 2026-04-20 | **INFRA GHOST FILE RESTORATION** | `nexus/infrastructure/`, `nexus/app/shadow_bus.py` | High | Git revert | Antigravity |
| 2026-04-20 | **GOVERNANCE STUB PURGE** | Entire Codebase | Low | Git revert | Antigravity |
| 2026-04-20 | **MSA REAL WIRING & DB UPSERT** | `nexus/core/router.py`, `nexus/experiments/msa_routing/` | Medium | Git revert | Antigravity |
| 2026-04-20 | **1-BIT CORE & GBNF HARDENING** | `nexus/core/onebit_core.py`, `nexus/core/drone_engine.py` | High | Git revert | Antigravity |
| 2026-04-19 | **GOVERNANCE DEADLOOP DECOUPLING** | `scripts/ops/ci_gate.py` | High | Git revert | Antigravity |
| 2026-04-19 | **NEXUS HARDENING STAGES A-G** | `nexus/governance/`, `nexus/core/lineage.py` | High | Git revert | Antigravity |
| 2026-04-18 | **DEEP PLAN/AUDIT GATES** | `scripts/ops/task_runner.py`, `nexus/engine/coordinator.py` | High | Git revert | Antigravity |
| 2026-04-18 | **RED-TEAM AUDIT HARDENING** | `compliance/audit/`, `scripts/ops/nexus_acceptance_check.py` | High | Git revert | Antigravity |
| 2026-04-18 | **V25.7 ULTRA-HARDENED BASELINE** | `nexus/core/`, `.nexus/config/` | High | Git revert | Antigravity |
| 2026-04-18 | **INTELLIGENCE INTERLOCK & COMPACTOR** | `nexus/core/context_compactor.py`, `nexus/core/bayesian_interlock.py` | High | Git revert | Antigravity |
| 2026-04-17 | **NEXUS ENFORCED GOVERNANCE HARDENING** | `nexus/engine/coordinator.py`, `scripts/ops/ci_gate.py`, `nexus/core/drone_protocol.py`, `nexus/core/drone_engine.py`, `nexus/core/hallucination_guard.py` | High | Git revert | Antigravity |
| 2026-04-17 | **LOCAL DRONE BRAIN (Bonsai)** | `nexus/core/drone_engine.py`, `Bonsai_Modelfile` | Low | Git revert | Gemini-Nexus |
| 2026-04-17 | **TACTICAL DRONE INTEGRATION** | `nexus/core/drone_engine.py`, `nexus/core/campaign_general.py`, `tests/core/test_drone_integration.py` | Medium | Git revert | Gemini-Nexus |
| 2026-04-17 | **CLI ENTRYPOINT UNIFICATION** | `scripts/engine/nexus_cli.py`, `scripts/ops/_nexus_enforced_briefing.sh`, `nexus_wiki_vault/06_Ops/NEXUS_ENFORCED_LAUNCH.md` | Low | Git revert | Gemini-Nexus |
| 2026-04-17 | **STARTUP ENFORCEMENT HARDENING** | `scripts/ops/start_gemini_nexus_enforced.sh`, `scripts/ops/start_codex_nexus_enforced.sh`, `scripts/ops/nexus_startup_contract_check.py` | Low | Git revert | Gemini-Nexus |
| 2026-04-17 | **POST-RELEASE ENHANCEMENT PACK** | `nexus/core/campaign_general.py`, `nexus/core/skill_assembler.py`, `tests/core/test_skill_jit_enhanced.py` | Low | Git revert | Gemini-Nexus |
| 2026-04-17 | **L1~L7 HARDENING ROUND 3 (P1/P2/P3)** | `nexus/core/campaign_general.py`, `nexus/core/skill_assembler.py`, `tests/e2e/test_l1_l7_pipeline_regression.py` | Low | Git revert | Gemini-Nexus |
| 2026-04-17 | **L1~L7 HARDENING ROUND 2 (P1/P2/P3)** | `nexus/core/campaign_general.py`, `nexus/core/criteria_builder.py`, `nexus/core/skill_assembler.py`, `tests/core/test_l1_l4_realization_v2.py` | Low | Git revert | Gemini-Nexus |
| 2026-04-17 | **L1~L7 REALIZATION PACK (P0/P1/P2)** | `nexus/core/campaign_general.py`, `nexus/core/skill_assembler.py`, `nexus/core/criteria_builder.py`, `tests/core/test_l1_l4_realization.py` | Low | Git revert | Gemini-Nexus |
| 2026-04-15 | **Learn Benchmark Curation & Launchd Production Scheduler** | `nexus/research/learn_mode.py`, `scripts/engine/nexus_cli.py`, `scripts/ops/learn_refresh_launchd.py`, `tests/test_cli_learn_mode.py`, `tests/ops/test_learn_refresh_launchd.py` | Low | Git revert | Codex |
| 2026-04-15 | **Learn Mode Autonomous Refresh Daemon** | `scripts/ops/learn_refresh_daemon.py`, `scripts/ops/start_learn_refresh_daemon.sh`, `scripts/ops/stop_learn_refresh_daemon.sh`, `scripts/ops/status_learn_refresh_daemon.sh`, `tests/ops/test_learn_refresh_daemon.py` | Low | Git revert | Codex |
| 2026-04-15 | **Learn Mode Benchmark Candidate Writeback & Refresh Planning** | `nexus/research/learn_mode.py`, `scripts/engine/nexus_cli.py`, `tests/test_cli_learn_mode.py` | Low | Git revert | Codex |
| 2026-04-21 | **Report Claims Domain Decoupling (Fail-Closed)** | `nexus/delivery/report_claims.py`, `scripts/ops/verify_report_claims.py` | Medium | Git revert | Codex |
| 2026-04-21 | **TDD Refactor: Delivery Evidence Parsing + Evidence Writer Modularization + RunDir Hygiene** | `scripts/ops/ci_gate.py`, `nexus/engine/pipeline_repair.py`, `nexus/services/reporter.py`, `tests/ops/test_ci_gate_delivery_tracked.py`, `tests/engine/test_pipeline_repair.py`, `tests/test_reporter.py` | Medium | Git revert | Codex |
| 2026-04-21 | **Engine Decomposition Wave: Routing/Repair/Event Queue Service Split** | `nexus/engine/coordinator.py`, `nexus/engine/*_service.py`, `nexus/events/signal_queue_service.py`, `nexus/research/learn/*_service.py`, `tests/engine/`, `tests/core/test_signal_queue_service.py` | Medium | Git revert | Codex |

### 🤖 Auto-Synthesized Governance Log
- **Target Modules**: scripts/ops/ci_gate.py
- **Semantic Pulse**: Automated safety synchronization triggered.
- **Diff Signature**: 6968860613178720067


### 🤖 Auto-Synthesized Governance Log
- **Target Modules**: scripts/ops/ci_gate.py
- **Semantic Pulse**: Automated safety synchronization triggered.
- **Diff Signature**: 2154708499925440376


### 🤖 Auto-Synthesized Governance Log
- **Target Modules**: scripts/ops/ci_gate.py
- **Semantic Pulse**: Automated safety synchronization triggered.
- **Diff Signature**: -5877691694954462213


### 🤖 Auto-Synthesized Governance Log
- **Target Modules**: scripts/ops/ci_gate.py
- **Semantic Pulse**: Automated safety synchronization triggered.
- **Diff Signature**: -2811823959556112911


### 🤖 Auto-Synthesized Governance Log
- **Target Modules**: scripts/ops/ci_gate.py
- **Semantic Pulse**: Automated safety synchronization triggered.
- **Diff Signature**: 7290610245957236671


### 🤖 Auto-Synthesized Governance Log
- **Target Modules**: scripts/ops/ci_gate.py
- **Semantic Pulse**: Automated safety synchronization triggered.
- **Diff Signature**: 3438110020721803203

## 2026-05-21 - Zero-Trust V2 M13-M19 fresh behavior runner boundary

| Date | Change | Evidence | Risk | Rollback | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-05-21 | Added fail-closed `capability_ab_runner` adapter matrix and M13-M19 completion report for V2 skill promotion. V1 remains runtime fallback; V1 evidence cannot count toward V2 promotion. | `nexus/learning/zero_trust_v2_behavior_adapter.py`, `scripts/ops/build_zero_trust_v2_behavior_runner_matrix.py`, `scripts/ops/build_zero_trust_v2_m13_m19_completion.py`, `docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUNNER_MATRIX_2026-05-21.json`, `docs/reports/NEXUS_ZERO_TRUST_V2_M13_M19_COMPLETION_2026-05-21.json` | Medium | Git revert; artifacts are reporting-only and keep `runtime_mutation_allowed=false` | Codex |

## 2026-05-21 - Zero-Trust V2 M20-M27 fresh task refs and V1 shutdown boundary

| Date | Change | Evidence | Risk | Rollback | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-05-21 | Added fresh task refs for 19 V2 candidates and M20-M27 completion verdict. Runner commands are now ready for physical behavior execution, but no signed receipts exist, so promotion, runtime mutation, public benchmark claims, and V1 shutdown remain blocked. | `scripts/ops/build_zero_trust_v2_fresh_task_refs.py`, `scripts/ops/build_zero_trust_v2_m20_m27_completion.py`, `docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_REFS_2026-05-21.json`, `docs/reports/NEXUS_ZERO_TRUST_V2_FRESH_TASK_MANIFEST_2026-05-21.json`, `docs/reports/NEXUS_ZERO_TRUST_V2_M20_M27_COMPLETION_2026-05-21.json` | Medium | Git revert; artifacts are non-mutating and keep V1 fallback active | Codex |

## 2026-05-21 - Zero-Trust V2 M28-M35 execution plan and closure gates

| Date | Change | Evidence | Risk | Rollback | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-05-21 | Added M28-M35 execution plan for one P0 canary preflight, 3-run signed behavior batch planning, receipt import gate, manual apply gate, canary rollback gate, P0/P1/P2 rollout sequencing, and V1 closure gate. The artifact remains non-mutating and blocks all promotion until clean signed V2 receipts exist. | `scripts/ops/build_zero_trust_v2_m28_m35_execution_plan.py`, `tests/ops/test_build_zero_trust_v2_m28_m35_execution_plan.py`, `docs/reports/NEXUS_ZERO_TRUST_V2_M28_M35_EXECUTION_PLAN_2026-05-21.json` | Medium | Git revert; no runtime mutation is performed | Codex |

## 2026-05-21 - Zero-Trust V2 M36-M44 preflight pass and promotion lock

| Date | Change | Evidence | Risk | Rollback | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-05-21 | Executed the M28 preflight canary, repaired runner contract blockers, and added M36-M44 completion gates. M36 now passes, but M38-M44 remain locked because no runtime-signed clean V2 behavior receipts exist. | `scripts/ops/build_zero_trust_v2_m36_m44_completion.py`, `tests/ops/test_build_zero_trust_v2_m36_m44_completion.py`, `.nexus/reports/zero_trust_v2_behavior/policy_capability_gate/browse/preflight/benchmark_preflight.json`, `docs/reports/NEXUS_ZERO_TRUST_V2_M36_M44_COMPLETION_2026-05-21.json` | Medium | Git revert; report artifacts are non-mutating and keep V1 fallback active | Codex |

## 2026-05-22 - Zero-Trust V2 M45-M52 canary behavior run fail-closed

| Date | Change | Evidence | Risk | Rollback | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-05-22 | Bound `runner_env` into behavior run plans, added a dry-run behavior execution hook, attempted the first canary behavior run, and added M45-M52 completion gates. The canary produced an evidence bundle but failed receipt import readiness, so manual apply, canary apply, P0/P1/P2 rollout, and V1 closure remain blocked. | `scripts/ops/run_zero_trust_v2_behavior_runs.py`, `scripts/ops/build_zero_trust_v2_m45_m52_completion.py`, `tests/ops/test_run_zero_trust_v2_behavior_runs.py`, `tests/ops/test_build_zero_trust_v2_m45_m52_completion.py`, `docs/reports/NEXUS_ZERO_TRUST_V2_BEHAVIOR_RUN_HOOK_2026-05-22.json`, `docs/reports/NEXUS_ZERO_TRUST_V2_M45_M52_COMPLETION_2026-05-22.json` | Medium | Git revert; no runtime mutation is performed and V1 fallback remains active | Codex |

## 2026-05-22 - Zero-Trust V2 unified mainline fail-closed closeout

| Date | Change | Evidence | Risk | Rollback | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-05-22 | Added a unified mainline closeout for M53-M64. The closeout keeps all milestones blocked because the canary lacks clean runtime-signed V2 receipts and 34 capability coverage. Runtime mutation, promotion credit, automatic apply, and public benchmark unlock all remain false. | `scripts/ops/build_zero_trust_v2_unified_mainline.py`, `tests/ops/test_build_zero_trust_v2_unified_mainline.py`, `docs/reports/NEXUS_ZERO_TRUST_V2_UNIFIED_MAINLINE_2026-05-22.json` | Medium | Git revert; artifact is non-mutating and keeps V1 fallback active | Codex |

## 2026-05-22 - Zero-Trust V2 runtime default overlay apply

| Date | Change | Evidence | Risk | Rollback | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-05-22 | Imported `102/102` clean runtime-signed V2 behavior receipts into promotion readiness, completed manual apply acknowledgement, promoted P0 and P1/P2 batches, generated the V2 default runtime overlay, and passed post-apply smoke for 34/34 capabilities. Public benchmark remains locked. | `scripts/ops/build_zero_trust_v2_behavior_evidence.py`, `scripts/ops/build_zero_trust_v2_runtime_apply.py`, `scripts/ops/build_zero_trust_v2_unified_mainline.py`, `docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-22.json`, `docs/reports/NEXUS_ZERO_TRUST_V2_RUNTIME_POST_APPLY_SMOKE_2026-05-22.json`, `docs/reports/NEXUS_ZERO_TRUST_V2_UNIFIED_MAINLINE_2026-05-22.json` | Medium | Restore `docs/reports/NEXUS_SF_FINAL_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-21.json` as runtime overlay and keep V1 fallback active | Codex |
