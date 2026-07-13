---
title: System Map
type: operational
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
verified_against_commit: 957cd19c744d168ff050667b611adca5fb20d56f
source_of_truth: repository evidence and current runtime reports
confidence: high
---

# System Map

The main components of Nexus, their responsibilities, authority levels, and known limitations.

## Component reference

| Component | Responsibility | Authority level | Code path | Primary caller | Input | Output | Evidence | Known limitation |
|-----------|---------------|----------------|-----------|---------------|-------|--------|----------|-----------------|
| Canonical CLI | User-facing command surface for governance operations | operational | `scripts/nexus_cli.py` | Human operator, Agent | CLI args | Command output, exit code | CLI tests | Not wired to LocalModelExecutor |
| CampaignGeneral | Task decomposition and P-X-D-R-A-C lifecycle orchestration | operational | `nexus/engine/campaign_general.py` | CLI, Runner | Task manifest | Phase artifacts | Unit tests | Depends on LLM for intent decomposition |
| NexusPipeline | End-to-end pipeline execution across phases | operational | `nexus/engine/pipeline.py` | CampaignGeneral | Phase inputs | Phase outputs | Pipeline tests | Sequential execution bottleneck |
| CapabilityPlanner | Selects capability combinations based on task signals | operational | `nexus/engine/capability_planner.py` | Pipeline, Router | Task context, phase | Selected capabilities | Route tests | Cannot add new routes without architecture authorization |
| SkillsRouter | Routes tasks to formal skills based on phase and signals | operational | `nexus/engine/skills_router.py` | CapabilityPlanner | Phase, signals | Selected skills | Router tests | Decision boundary limited to known skills |
| CapabilitySelector | Final skill selection from router candidates | operational | `nexus/engine/capability_selector.py` | SkillsRouter | Skill candidates | Selected skill | Selector tests | No learning from past selections |
| LocalModelExecutor | Local model execution with topology dispatch | operational | `nexus/engine/local_model_executor.py` | Benchmark scripts (primary) | Task, topology | Candidate, receipt | Benchmark tests | Not accessible from Canonical CLI |
| HealOrchestrator | Coordinates self-healing and repair actions | operational | `nexus/services/local_heal/heal_orchestrator.py` | Pipeline, LocalHeal | Failure signature | Repair plan | Heal tests | Limited to known repair patterns |
| CommitteeOrchestrator | Multi-agent committee governance and voting | operational | `nexus/engine/committee_orchestrator.py` | Pipeline | Proposal | Committee decision | Committee tests | Committee composition is static |
| CloudAgentAdapter | Cloud agent integration layer | contract | `nexus/services/cloud_agent_adapter.py` | Pipeline | Task context | Cloud agent response | Contract tests | Uses fake cloud in World B |
| Verifier | Validates artifacts against contracts | normative | `nexus/core/verifier.py` | Audit phase | Artifact, contract | Pass/fail, receipt | Verifier tests | Cannot be weakened |
| Candidate Isolation Gate | Ensures candidate providers are isolated | normative | `nexus/core/candidate_isolation.py` | LocalModelExecutor | Candidates | Isolated candidates | Isolation tests | Benchmark path only |
| Claim Gate | Validates claims against evidence thresholds | normative | `nexus/core/claim_gate.py` | Verifier | Claim, evidence | Claim verdict | Gate tests | Cannot be weakened |
| Evidence Bundle | Collects and packages evidence artifacts | operational | `nexus/core/evidence_bundle.py` | Verifier, Audit | Evidence sources | Bundled evidence | Bundle tests | May include stale artifacts |
| Learning Closure | Extracts lessons from task outcomes and writes back | operational | `nexus/services/learning_closure.py` | Crystallize phase | Task outcome, lessons | Learning entries | Learning tests | Depends on successful task completion |
| Wiki Sync | Synchronizes Wiki with codebase state | operational | `scripts/ops/wiki_sync_check.py` | CI gate, ops | Code changes | Wiki updates | Sync tests | May drift if not run regularly |

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
