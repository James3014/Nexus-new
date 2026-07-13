---
title: Task Router
type: operational
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
verified_against_commit: 957cd19c744d168ff050667b611adca5fb20d56f
source_of_truth: repository evidence and current runtime reports
confidence: medium
---

# Task Router

Navigate Nexus by task type rather than by directory. For each task class, this page tells you what to read first, where the code lives, and what evidence is required. Every code entry has been physically verified.

## Task routing table

| Task type | Read first | Code entry (verified) | Inspection tool | Forbidden shortcut | Verification | Claim ceiling |
|-----------|-----------|----------------------|----------------|-------------------|-------------|---------------|
| Route or CapabilityPlanner change | CURRENT_STATE, SYSTEM_ARCHITECTURE_BLUEPRINT | `nexus/engine/capability_planner.py` (exists) + `scripts/core/skills_router.py` (exists) | `gitnexus_impact` (upstream + downstream) | Adding route without architecture authorization | Full route test suite | CONTRACT_VERIFIED |
| LocalHeal change | CURRENT_STATE, LocalHeal architecture docs | `nexus/services/local_heal/` (directory: local_model_executor.py, committee_orchestrator.py, isolated_verifier.py, claim_delivery_gate.py, learning_closure_bridge.py) | `gitnexus_impact` | Claiming runtime invocation without benchmark evidence | Unit + contract tests | CONTRACT_VERIFIED |
| Committee change | CURRENT_STATE, governance docs | `nexus/services/local_heal/committee_orchestrator.py` (exists) | `gitnexus_impact` | Weakening committee isolation | Committee test suite | CONTRACT_VERIFIED |
| Verifier or claim gate change | CURRENT_STATE, CLAIM_TAXONOMY | `nexus/services/local_heal/isolated_verifier.py` (World C) + `nexus/services/local_heal/claim_delivery_gate.py` (exists) | `gitnexus_impact` | Weakening verifier or claim gate | Gate test suite | CONTRACT_VERIFIED |
| Benchmark task | CURRENT_STATE, benchmark methodology | `scripts/bench/` (directory, exists) + `nexus/benchmark/` (directory, exists) | Benchmark scripts | Citing benchmark as product runtime | Reproducible benchmark run | BENCHMARK_VERIFIED |
| Wiki update | CURRENT_STATE, relevant source pages | `nexus_wiki_vault/` | Manual review | Claiming alignment without code evidence | Link check + frontmatter validation | DOCUMENTED |
| Security change | CURRENT_STATE, governance charter | `nexus/orchestrator/` + `nexus/verifiers/` | Security audit tools | Weakening security controls | Security review receipt | CONTRACT_VERIFIED |
| Performance optimization | CURRENT_STATE, complexity report | Target module | `gitnexus_impact`, profiler | Claiming production performance without load test | Before/after benchmark | BENCHMARK_VERIFIED |
| Research-only task | CURRENT_STATE, relevant sources | Read-only | Read-only tools | Making code changes | Research report | DOCUMENTED |
| Release or closeout task | CURRENT_STATE, ops docs | `scripts/ops/ci_gate.py` (exists) | CI gate scripts | Skipping verification gates | Full CI gate pass | CONTRACT_VERIFIED |

## Release claim ceiling note

A full CI gate pass alone does not prove PRODUCTION_READY. Per CLAIM_TAXONOMY.md, PRODUCTION_READY additionally requires:
- Reliability requirements met
- Security audit passed
- Load testing completed
- Monitoring in place
- Operational readiness confirmed
- Deployment conditions satisfied

The claim ceiling for release/closeout is CONTRACT_VERIFIED (or RUNTIME_INVOKED when an actual runtime receipt exists).

## Unresolved authority in code entries

| Task type | Authority uncertainty |
|-----------|----------------------|
| Route or CapabilityPlanner change | `scripts/core/skills_router.py` is the only SkillsRouter implementation; no `nexus/engine/skills_router.py` exists |
| Verifier or claim gate change | Different verifier stacks for World C (`isolated_verifier.py`) vs domain verifiers (`nexus/verifiers/`); no single canonical path |
| Claim gate | `claim_delivery_gate.py` exists but no single `nexus/core/claim_gate.py`; concept spans multiple files |

## How to use this table

1. Identify your task type from the left column.
2. Read the specified documents before touching code.
3. Use the listed inspection tool to assess blast radius.
4. Follow the verification steps exactly.
5. Do not claim above the listed claim ceiling.

## Related pages

- [CURRENT_STATE](CURRENT_STATE.md) - what is proven
- [AGENT_BOOTSTRAP](AGENT_BOOTSTRAP.md) - full startup sequence
- [CLAIM_TAXONOMY](../01_System/CLAIM_TAXONOMY.md) - evidence thresholds
- [SYSTEM_MAP](SYSTEM_MAP.md) - component reference
