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

## One-sentence summary
記錄 Nexus 治理架構的所有重大變更、審計硬化與契約遷移歷史。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- **歷史溯源**: 提供系統治理邏輯演化的完整 Traceability。 [Source: scripts/ops/ci_gate.py]
- **風險管理**: 記錄每次變更的風險等級與回滾計畫，確保治理硬化的穩定性。

## Governance Change History (治理變更歷史)

| Date | Change (項) | Affected Components | Risk | Rollback Plan | Verifier |
|---|---|---|---|---|---|
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
