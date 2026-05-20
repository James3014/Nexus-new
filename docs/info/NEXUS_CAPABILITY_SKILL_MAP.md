# Nexus 能力與 Skill 映射表 (2026-05-20)

> [!NOTE]
> 本文件由 `scripts/ops/build_heep_emas_pipeline.py` 依據 SF SSOT 與 HEEP/EMAS contract 自動生成。
> HEEP 結果目前是 deterministic local dry-run；runtime default 與 public benchmark 仍需獨立 gate。

## 映射總表

| 能力 (Capability) | 當前主技能 (Primary Skill ID) | HEEP Mode | EMAS Assembly | Evidence |
| :--- | :--- | :--- | :--- | :--- |
| `artifact_gate` | `sf-systematic-artifact_gate-differential-review-461fbd0c` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `autonomic_router` | `sf2-autonomic_router-route-fit-spec` | **Mode B (Guard)** | primary=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `autoreason` | `sf2-belief-route-fit-spec` | **Mode B (Guard)** | primary=sf2-belief-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `belief` | `sf2-belief-route-fit-spec` | **Mode B (Guard)** | primary=sf2-belief-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `benchmark_meta_opt` | `sf-systematic-benchmark_meta_opt-hugging-face-trackio-d21c6b90` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf-systematic-benchmark_meta_opt-hugging-face-trackio-d21c6b90, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `claim_gate` | `nexus-benchmark-continuous-optimization` | **Mode B (Guard)** | primary=nexus-benchmark-continuous-optimization, Logic=sf2-autonomic_router-route-fit-spec | receipt-backed SF root |
| `codeintel` | `sf-systematic-codeintel-first-principles-thinking-f95019ea` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `ddtree` | `nexus-root-cause-probe` | **Mode B (Guard)** | primary=nexus-root-cause-probe, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `direct_master_loop` | `sf-systematic-direct_master_loop-build-32802a87` | **Mode A (Solo)** | primary=sf-systematic-direct_master_loop-build-32802a87 | receipt-backed SF root |
| `drone` | `sf-systematic-drone-python-background-jobs-18326a62` | **Mode A (Solo)** | primary=sf-systematic-drone-python-background-jobs-18326a62 | receipt-backed SF root |
| `external_productivity` | `sf-systematic-external_productivity-writer-77dc7840` | **Mode A (Solo)** | primary=sf-systematic-external_productivity-writer-77dc7840 | receipt-backed SF root |
| `file_lock_security_gate` | `sf2-file_lock_security_gate-route-fit-spec` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf2-file_lock_security_gate-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `forecast_pregate` | `create-plan` | **Mode B (Guard)** | primary=create-plan, Logic=sf2-autonomic_router-route-fit-spec | receipt-backed SF root |
| `governance_and_trust` | `sf-systematic-governance_and_trust-aegisops-ai-0aa841e2` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-governance_and_trust-aegisops-ai-0aa841e2 | receipt-backed SF root |
| `hyper_sprint` | `sf2-hyper_sprint-route-fit-spec` | **Mode A (Solo)** | primary=sf2-hyper_sprint-route-fit-spec | receipt-backed SF root |
| `lancedb` | `research-source-validation-auditor` | **Mode B (Guard)** | primary=research-source-validation-auditor, Logic=sf2-autonomic_router-route-fit-spec | receipt-backed SF root |
| `learn_ask` | `github8-skilless-deep-research-learn-ask` | **Mode C (Swarm)** | Scout=github8-skilless-deep-research-learn-ask, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `learning_closure` | `sf-systematic-learning_closure-memory-lint-8bdb0fca` | **Mode C (Swarm)** | Scout=sf-systematic-learning_closure-memory-lint-8bdb0fca, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `memory` | `sf-systematic-memory-project-skill-audit-cc8b7621` | **Mode B (Guard)** | primary=sf-systematic-memory-project-skill-audit-cc8b7621, Logic=sf2-autonomic_router-route-fit-spec | receipt-backed SF root |
| `mempalace` | `sf2-mempalace-route-fit-spec` | **Mode B (Guard)** | primary=sf2-mempalace-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `metabolism_resume` | `github-auto-skill-safe-learning` | **Mode A (Solo)** | primary=github-auto-skill-safe-learning | receipt-backed SF root |
| `nightshift` | `sf2-nightshift-route-fit-spec` | **Mode A (Solo)** | primary=sf2-nightshift-route-fit-spec | receipt-backed SF root |
| `policy_capability_gate` | `sf-systematic-policy_capability_gate-aegisops-ai-0aa841e2` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-policy_capability_gate-aegisops-ai-0aa841e2 | receipt-backed SF root |
| `registry_skills_sync` | `github5-skill-seekers-safe-registry-builder` | **Mode B (Guard)** | primary=github5-skill-seekers-safe-registry-builder, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `regression_guard` | `sf-systematic-regression_guard-odoo-automated-tests-dad98433` | **Mode B (Guard)** | primary=sf-systematic-regression_guard-odoo-automated-tests-dad98433, Logic=sf2-autonomic_router-route-fit-spec | receipt-backed SF root |
| `repair_loop` | `sf-systematic-repair_loop-odoo-automated-tests-dad98433` | **Mode B (Guard)** | primary=sf-systematic-repair_loop-odoo-automated-tests-dad98433, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `research` | `sf-systematic-research-research-lookup-7e6f92a0` | **Mode C (Swarm)** | Scout=sf-systematic-research-research-lookup-7e6f92a0, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `research_and_source_discipline` | `research-citation-chain-verifier` | **Mode C (Swarm)** | Scout=research-citation-chain-verifier, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `research_control_plane` | `sf-systematic-research_control_plane-research-lookup-7e6f92a0` | **Mode C (Swarm)** | Scout=sf-systematic-research_control_plane-research-lookup-7e6f92a0, Logic=sf2-autonomic_router-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `sandbox_replay` | `sf2-sandbox_replay-route-fit-spec` | **Mode B (Guard)** | primary=sf2-sandbox_replay-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `swarm_multi_agent` | `sf2-swarm_multi_agent-route-fit-spec` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf2-swarm_multi_agent-route-fit-spec, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `ui_validator` | `sf-systematic-ui_validator-e2e-testing-d98eb7c3` | **Mode B (Guard)** | primary=sf-systematic-ui_validator-e2e-testing-d98eb7c3, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |
| `ultra_review` | `github11-vulnerability-scanner-ultra-review` | **Mode C (Swarm)** | Scout=sf-systematic-codeintel-first-principles-thinking-f95019ea, Logic=sf2-autonomic_router-route-fit-spec, Audit=github11-vulnerability-scanner-ultra-review | receipt-backed SF root |
| `xray` | `diagnose` | **Mode B (Guard)** | primary=diagnose, Audit=sf-systematic-artifact_gate-differential-review-461fbd0c | receipt-backed SF root |

## 邊界
- Mode A/B/C 是 HEEP local evaluation policy，不是 public benchmark claim。
- EMAS Safe-Candidate 不會自動 promotion 到 runtime default。
- 任何 runtime apply 仍需 runtime-confirmed selected/injected/used/evidence/gate/outcome receipt。

---
*Generated by Nexus HEEP/EMAS pipeline.*
