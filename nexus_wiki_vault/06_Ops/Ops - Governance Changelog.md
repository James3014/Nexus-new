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
| 2026-05-20 | **HEEP MAT-B Receipt Executor Repair: explicit blocker queue and swarm bench executor env for drone/nightshift/swarm rows** | `scripts/ops/build_heep_mat_b_blocker_resolution_queue.py`, `scripts/ops/build_heep_flash_nexus_compare_matrix.py`, `docs/reports/NEXUS_HEEP_MAT_B_BLOCKER_RESOLUTION_QUEUE_2026-05-20.json`, `docs/plans/NEXUS_HEEP_EVALUATION_PLAN.md`, `tests/ops/` | Medium | Git revert | Codex |
| 2026-05-20 | **Routing Spec V2 Closure: RLM handoff receipt, OutcomeMemory trust-clean soak, dispatcher plan consume, mutation assurance read-model gate** | `nexus/engine/rlm_controller.py`, `nexus/app/research_flow_service.py`, `nexus/learning/outcome_memory.py`, `nexus/engine/route_runtime_dispatcher.py`, `scripts/ops/build_claim_evidence_read_model.py`, `tests/` | Medium | Git revert | Codex |
| 2026-05-20 | **RLM Bounded Orchestration Adapter: X/R-loop receipts without recursive dispatch or public/runtime unlock** | `nexus/engine/rlm_controller.py`, `nexus/app/research_flow_service.py`, `nexus/contracts/routing_spec_v2_backlog.py`, `tests/engine/test_rlm_outcome_integration.py`, `tests/contracts/test_routing_spec_v2_backlog.py`, `docs/plans/` | Medium | Git revert | Codex |
| 2026-05-20 | **Full CI Eval Policy Semantics: percent-style threshold normalization and warn-only eval gate behavior** | `nexus/core/gate_evaluator.py`, `scripts/ops/ci_gate.py`, `tests/core/test_gate_evaluator_policy.py`, `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md` | Medium | Git revert | Codex |
| 2026-05-20 | **Full CI Wiki Governance Scope: legacy/report/archive soft-contract classification for full gate pass** | `scripts/ops/wiki_linter.py`, `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md`, `nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md` | Medium | Git revert | Codex |
| 2026-05-20 | **Full CI Transient Artifact Cleanup: restore known tracked generated outputs on success** | `scripts/ops/ci_gate.py`, `tests/ops/test_ci_gate_closeout_contract.py`, `docs/plans/NEXUS_OPTIMIZATION_PLAN_CONTEXT_LEARNING_HARNESS_2026-05-19.md`, `nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md` | Low | Git revert | Codex |
| 2026-05-20 | **Non-Swarm/NSP Refactor Closure: CompletionEnvelope read-model validation and evidence union-merge guard** | `nexus/contracts/claim_evidence_read_model.py`, `nexus/contracts/evidence_retention.py`, `scripts/ops/build_claim_evidence_read_model.py`, `tests/contracts/`, `tests/ops/`, `tests/core/`, `docs/plans/` | Low | Git revert | Codex |
| 2026-05-20 | **Routing Refactor Boundary Gates: Context adapter fail-closed, AutonomicRouter-forward DAG serialization, routing spec v2 forbidden-path backlog gate** | `nexus/core/context_runtime_adapter.py`, `nexus/contracts/route_dag_pregate.py`, `nexus/contracts/routing_spec_v2_backlog.py`, `tests/contracts/`, `tests/core/`, `docs/reports/`, `docs/plans/` | Medium | Git revert | Codex |
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
