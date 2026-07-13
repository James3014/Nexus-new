---
title: System Map
type: operational
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
content_verified_against_commit: a2ae57ab96a9ddb0243858f4f2c1776709511af5
document_updated_in_commit: fecda71e417c453a7ea2ae0229478784921c362a
source_of_truth: repository evidence and current runtime reports
confidence: medium
---

# System Map

The main components of Nexus, their responsibilities, authority levels, and known limitations. Every code path in this page has been physically verified against the repository.

## Core component map

| # | Component | Responsibility | Authority level | Verified path | Primary caller | Known limitation |
|---|-----------|---------------|----------------|---------------|---------------|-----------------|
| 1 | Canonical CLI | User-facing command surface for governance operations | operational | `scripts/nexus_cli.py` (public wrapper) -> `scripts/engine/nexus_cli.py` (canonical implementation) | Human operator, Agent | Not wired to LocalModelExecutor |
| 2 | CampaignGeneral | Task decomposition and P-X-D-R-A-C lifecycle orchestration | operational | `nexus/core/campaign_general.py` | CLI, Runner | Depends on LLM for intent decomposition |
| 3 | NexusPipeline | End-to-end pipeline execution across phases | operational | `nexus/engine/pipeline.py` | CampaignGeneral | Sequential execution bottleneck |
| 4 | CapabilityPlanner | Selects capability combinations based on task signals | operational | `nexus/engine/capability_planner.py` | Pipeline, Router | Cannot add new routes without architecture authorization |
| 5 | SkillsRouter | Routes tasks to formal skills based on phase and signals | operational | `scripts/core/skills_router.py` | CapabilityPlanner | Decision boundary limited to known skills |
| 6 | CapabilitySelector | Final skill selection from router candidates | operational | `nexus/core/capability_selector.py` (primary) / `nexus/engine/capability_selector.py` (compatibility shim) | SkillsRouter | No learning from past selections |
| 7 | LocalModelExecutor | Local model execution with topology dispatch | operational | `nexus/services/local_heal/local_model_executor.py` | Benchmark scripts, LocalAssistService | Not accessible from Canonical CLI (Gap 1) |
| 8 | HealOrchestrator | Coordinates self-healing and repair actions | operational | `nexus/services/local_heal/` (directory) | Pipeline, LocalHeal | Limited to known repair patterns |
| 9 | CommitteeOrchestrator | Multi-agent committee governance and voting | operational | `nexus/services/local_heal/committee_orchestrator.py` | Pipeline, LocalModelExecutor | Committee composition is static |
| 10 | CloudAgentAdapter | Cloud agent integration layer | contract | `nexus/services/cloud_agent_cli_adapter.py` / `nexus/services/cloud_agent_contract.py` | Pipeline | Uses fake cloud in World B (Gap 3) |
| 11 | Verifier | Validates artifacts against contracts | normative | `nexus/services/local_heal/isolated_verifier.py` (World C) / `nexus/verifiers/` (domain verifiers) | Audit phase | Cannot be weakened |
| 12 | Candidate Isolation Gate | Ensures candidate providers are isolated | normative | `nexus/services/local_heal/isolated_local_solve_loop.py` | LocalModelExecutor | Benchmark path only |
| 13 | Claim Gate | Validates claims against evidence thresholds | normative | `nexus/services/local_heal/claim_delivery_gate.py` | Verifier | Cannot be weakened |
| 14 | Evidence Bundle | Collects and packages evidence artifacts | operational | `nexus/orchestrator/evidence_collector.py` / `nexus/orchestrator/evidence_policy.py` | Verifier, Audit | May include stale artifacts |
| 15 | Learning Closure | Extracts lessons from task outcomes and writes back | operational | `nexus/services/local_heal/learning_closure_bridge.py` | Crystallize phase | Depends on successful task completion |
| 16 | Wiki Sync | Synchronizes Wiki with codebase state | operational | `scripts/ops/wiki_sync_check.py` | CI gate, ops | May drift if not run regularly |

## CLI wrapper and implementation roles

| File | Role | Evidence |
|------|------|----------|
| `scripts/nexus_cli.py` | Public wrapper: imports and delegates to `scripts.engine.nexus_cli.nexus` | File content: 4-line wrapper with `from scripts.engine.nexus_cli import nexus` |
| `scripts/engine/nexus_cli.py` | Canonical CLI implementation: Click commands, SanitizedRunner, all CLI logic | File content: 600+ lines, main entry point |

## Multiple-authority collisions

| Component | Primary path | Secondary path | Authority status |
|-----------|-------------|---------------|-----------------|
| CapabilitySelector | `nexus/core/capability_selector.py` (learning policy loader) | `nexus/engine/capability_selector.py` (compatibility shim, delegates to planner) | Resolved: core is primary, engine is compatibility wrapper |
| Verifier | `nexus/services/local_heal/isolated_verifier.py` (World C) | `nexus/verifiers/` (domain-specific verifiers) | Unresolved: different verifier stacks for different worlds |
| Claim Gate | `nexus/services/local_heal/claim_delivery_gate.py` | No single `nexus/core/claim_gate.py` exists | Unresolved: claim gate concept spans multiple files |
| Evidence | `nexus/orchestrator/evidence_collector.py` | `nexus/orchestrator/evidence_policy.py` | Unresolved: collector vs policy authority split |
| Learning Closure | `nexus/services/local_heal/learning_closure_bridge.py` | No single `nexus/services/learning_closure.py` exists | Resolved: bridge is the physical implementation |

## Component count vs physical file count

| Metric | Count |
|--------|-------|
| Components mapped | 16 |
| Verified physical files | 18 (some components have multiple files) |
| Verified caller relationships | 12 |
| Unresolved authority collisions | 3 (Verifier stacks, Claim Gate span, Evidence split) |

Physical file existence has been checked for all mapped paths. Caller and authority relationships remain only partially verified: 12 verified caller relationships across 16 mapped components. Three authority collisions remain unresolved and require architecture decisions.

## World-specific component availability

| Component | World A | World B | World C |
|-----------|---------|---------|---------|
| Canonical CLI | Yes | No | No |
| CampaignGeneral | Yes | No | No |
| CapabilityPlanner | Yes (route selection) | Yes (with_nexus arm) | Yes |
| LocalModelExecutor | **No** (Gap 1) | Yes | Yes |
| Verifier | Yes (governance) | Yes (claim verification) | Yes |
| Candidate Isolation | No | Yes | Yes |

## Related pages

- [TASK_ROUTER](TASK_ROUTER.md) - navigate by task type
- [GLOSSARY](GLOSSARY.md) - term definitions
- [System Overview](System Overview.md) - architecture and three worlds
- [CURRENT_STATE](CURRENT_STATE.md) - what is proven
