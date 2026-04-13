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

## One-sentence summary
記錄 Nexus 治理架構的所有重大變更、審計硬化與契約遷移歷史。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Role / responsibility
- **歷史溯源**: 提供系統治理邏輯演化的完整 Traceability。 [Source: scripts/ops/ci_gate.py]
- **風險管理**: 記錄每次變更的風險等級與回滾計畫，確保治理硬化的穩定性。

## Governance Change History (治理變更歷史)

| Date | Change (項) | Affected Components | Risk | Rollback Plan | Verifier |
|---|---|---|---|---|---|
| 2026-04-13 | **Research 2.0 Gladiator & Memory Metabolism Integration** | `nexus/research/`, `nexus/engine/policies/`, `nexus_cli.py` | Mid | Git revert | Antigravity |
| 2026-04-13 | **Automated Nexus Repair (AOS-P0-P1)** | `scripts/engine/`, `tests/engine/` | Mid | Git revert | Antigravity |
| 2026-04-11 | **Tiered Test Strategy & Control-Plane Docs** | `tests/research/`, `docs/research/`, `nexus_cli.py` | Low | Git revert | Antigravity |
| 2026-04-10 | **Semantic Path Containment & Zero-Overshoot Budget** | `nexus/research/selector_rollback.py`, `nexus/research/unified_evaluator.py` | High | Git revert | Antigravity |
| 2026-04-09 | **Article Organizer v1.5.0 & Localized Wiki Crystallization** | `scripts/ops/`, `.nexus/config/` | Low | Git revert | Antigravity |
| 2026-04-08 | **Stabilize LanceDB Index Idempotency** | `nexus/services/memory_indexer.py` | Low | Git revert | Antigravity |
| 2026-04-07 | **DeepScientist Research Integration** | `nexus/research/`, `nightshift.py`, `nexus_cli.py` | Low | Git revert | Antigravity |
| 2026-04-07 | **Gemini Invocation Reliability Hardening** | `scripts/ops/gemini_nexus_invoke.py`, `AGENT_PROTOCOL_v2.md` | Low | Git revert | Codex |
| 2026-04-06 | **Phase 3b: De-noising & Refinement Final Close-out** | `wiki_drift_audit`, `truth_claims`, `[Module - State Contracts](../02_Modules/Module - State Contracts.md)` | Low | Git revert | Antigravity |
| 2026-04-06 | **WS-B/C: Core Subdomain Deep-Mapping** | `nexus/core`, Wiki Vault | Low | Git revert | Antigravity |
| 2026-04-06 | **WS-F: Navigation Refactoring & Orphan Cleanup** | `[System Overview](../00_Home/System Overview.md).md`, Navbar | Low | Git revert | Antigravity |
| 2026-04-06 | **Governance Hardening Final** | **Global Coverage 86.0%, Keypath 100%, P1 Noise 11** | Mid | Git revert | Antigravity |
| 2026-04-05 | 核心模組深映射 | 完成 Orchestrator/Guard/Memory/Policy 深度映射頁。 | Pass 7 (Part 1) |
| 2026-04-06 | 治理全面硬化 | **Coverage 提升至 90.73%**，建立 20 案故障手冊與全量腳本索引。 | Pass 7 Final |
 全庫 Wiki, [CI Gate](Ops - CI/CD Promotion Gate.md), Reports | Mid | Git revert to HEAD~5 | Antigravity |

## Upstream
- **[CI Gate](Ops - CI/CD Promotion Gate.md)**: 提供自動變更觸發與驗證環境。 [Source: scripts/ops/ci_gate.py]

## Downstream
- **[System Overview](../00_Home/System Overview.md)**: 提供最新治理狀態的摘要。
- **[[Ops - CI/CD Promotion Gate]]**: 作為發版前「變更稽核」的參考。

## Related modules / files
- `.nexus/reports/`: 包含各項掃描的自動化證據。 [Source: scripts/ops/ci_gate.py]

## Source notes
- v22 Engine Spec: 要求「凡治理變更必有記錄，凡記錄必有回標」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Auto-[[logging]]**: 未來是否由 `ci_gate` 在成功 Promotion 後自動 Append 一筆紀錄到本頁。
- [ ] **Rollback Automation**: 何時實作「一鍵治理版本回滾」腳本。


---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]- [2026-04-08] 物理淨化：執行依賴解耦與路徑動態化 (Phase 3 Purge)。
## [2026-04-09] Governance Suite Restoration
- **CLI**: Restored `nexus:status`, `nexus:acceptance-check`, and `nexus:contract-check`.
- **OPS**: Added `--json` support to `nexus_acceptance_check.py`.
- **NAS**: v0.7 engine entities integrated into core governance.
## [2026-04-09] v0.9 Federated Learning Ignition
- **Phase**: Transition from Meta-Learning (v0.8) to Federated Averaging (v0.9).
- **Scope**: Multi-tenant DNA aggregation (FedAvg) + Differential Privacy (DP).
- **Scale**: Target 5000+ virtual swarm nodes.

## [2026-04-09] v23.7 Fleet Command & Sensory Sensory Expansion
- **Fleet Command**: Implemented `SupervisorEngine` for task decomposition and multi-tenant delegation.
- **Sensory Expansion**: Integrated `StyleIngester` for automated `DESIGN.md` updates from external URLs.
- **Reliability**: Launched `Checkpointing` and `nexus resume` for physical task recovery.
- **Protocol**: Enabled `MCP Server` for standardizing knowledge resource access.


## [2026-04-09] Physical Integrity Hardening
- **CI Gate**: Implemented `run_integrity_check` to scan for core class/method life-signs.
- **Safety**: Added `smoke_test_all.sh` for cross-generation functional validation.
- **Enforcement**: Mandatory life-sign check before any release or promotion.

## [2026-04-10] Nexus v24.2: Hierarchical Promotion & Interaction Validation
- **Protocol (v24.2)**: Established the Three-Tier Evolution Filter (Ring -> Interaction -> System).
- **Core (Hardening)**:
    - `BayesianEngine`: Upgraded to v24.2 with Cholesky Jitter Fallback and $O(N)$ variance computation. 
    - `ContextHub`: Now consumes `global_nas_aggression` directly from policy.
    - `LearningGate`: Now enforces `system_entropy_tolerance` as a hard block.
- **Verification**: 
    - Launched `interaction_validator.py` for real pairwise coupling tests.
    - Verified "High Aggression x Strict Entropy" scenario with zero degradation.
- **Artifacts**: NightShift success record at `tracelog_optimize-bayes-brain.jsonl`.
- **S2 (Performance)**: Upgraded `memory_indexer.py` to incremental `merge_insert`, reducing vector indexing I/O overhead.
- **S3 (Security)**: Hardened `federated_lessons.py` with strict type sanitization and truncation for multi-tenant data safety.
- **S4 (Availability)**: Integrated Circuit Breaker patterns in `prompt_builder.py` to ensure core prompt generation stability.
- **S5 (Intelligence)**: Activated dynamic belief revision linkage in the learning loop, enabling autonomous "belief rescission" upon failure.
- **Evolution**: Optimized LanceDB lookup logic to support newer response models (ListTablesResponse).

## [2026-04-09] Web UI Explorer (Page-Agent) Integration
- **Mechanism**: Implemented Text-DOM Mapping derived from `alibaba/page-agent` to provide low-token, vision-free web understanding.
- **Engine**: Added `WebDomMapper` for recursive interactive node identification and `WebActionExecutor` for mapping Agent JSON intent to Playwright physical actions.
- **Evidence**: Forced screenshot preservation for every autonomous step into `.nexus/reports/screenshots/`.
- **Skill**: Updated `ui-validator` to support `--agentic-mode`, enabling natural language task execution (e.g., "Click the submit button and check for error messages").
- **Verification**: Verified via `tests/core/test_web_dom_mapper.py` and E2E functional trace over local assets.

## [2026-04-09] Global Metabolism & Architecture Segregation (Hardening)
- **Metabolism**: Successfully deployed `@nexus_metabolize` decorator to 9 core Ops scripts (`ui-validator`, `ci_gate`, `task_scheduler`, etc.), enabling autonomous session distillation.
- **Segregation**: Performed "Physical Purge" of the repository. Identified and migrated 67 "Brain Application" scripts (librarian, brain_sync, etc.) to the decoupled `le-wm` workspace.
- **Inventory**: Completed a global health audit of the remaining 349 Nexus scripts; 100% syntax and entry-point verification pass.
- **State**: Restored missing `task_manifest.yaml` and resolved `uv` environment dependencies in the legacy scheduler logic.

## [2026-04-09] Phase 8: Autonomous Integrity & Protocol v2.1 Enforcement
- **Components**: Deployed `output_guard.py`, `autonomous_repair_loop.py`, `rollback_guard.py`, and `critique_engine.py`.
- **Integrity**: Integrated Physical Context Shield (2000-line hard truncation) into `ci_gate.py`.
- **Governance**: Implemented 🛡️ AGENT Enforcement Protocol v2.1 (Production-Hardened) with mandatory Physical Preflight.
- **Resilience**: Established Git-based rollback protection at round 3 of the autonomous repair loop.
- **Verification**: 100% success on 35/35 integration stress test scenarios.
## [2026-04-09] CI Dependency Recovery & PEP 621 Standard
- **Resolution**: Restored 28+ missing core dependencies (pydantic, torch, web3, etc.) following an incomplete PEP 621 migration.
- **Hardening**: Standardized `pyproject.toml` using the `[project]` table for enhanced `uv` and CI/CD compatibility.
- **NightShift**: Restored autonomous research cycles by removing broken visualization dependencies and correcting lockfile versions.
- **Verification**: Passed 🛡️ Verification Matrix (Acceptance + Contract + CI Gate).

## [2026-04-10] Night Shift Governance Hardening & Wisdom Triad Integration
- **Approval Gate**: Implemented `.nexus/nightshift/pending.json` for secure optimization harvesting and human-in-the-loop governance.
- **Auto-Sync**: Developed `_update_manifest_status` to automatically sync `task_manifest.yaml` upon approval, generating `docs(governance)` commits.
- **Wisdom Triad**: Integrated `MemPalace` (Ethics) with `LanceDB` (History) and `Memory` (Lessons) into the `PromptBuilder` engine.
- **Execution**: Upgraded `nightshift.py` to use the unified 3-layer context injection, improving repair correctness and architectural alignment.
- **Verification**: 100% success on triple context injection verification and manual approve-harvest-sync cycles.

## [2026-04-11] NightShift Physical Convergence Cleanup & Compatibility Closure
- **Scope**: Consolidated NightShift physical-run outputs into merge-ready changes and removed untracked experimental artifacts from the working tree.
- **Model Policy**: Confirmed primary `gemini-3.1-pro-preview` with fallback `gemini-3-flash-preview`; flash quota exhaustion now treated as capacity signal with failover/early-stop behavior.
- **Convergence Ops**: Re-ran 7 critical targets with timing telemetry and classified outcomes into `IMPROVED`, `CONVERGED`, and `NO_NEW_TRACE`.
- **Compatibility Fix**: Patched `CapabilityGate.get_tools` to safely handle `None`/empty/non-string phase inputs, restoring `self_evolve` path stability.
- **Lessons (Writeback)**:
  1. Generation success is insufficient without audit API compatibility checks (`DualTrackAudit` signature drift can invalidate rounds post-generation).
  2. Batch optimization requires strict artifact hygiene; traces and mock-path residue must be cleaned before merge review.
  3. Contract check requires a valid JSON contract payload; YAML task manifests are not drop-in substitutes.
